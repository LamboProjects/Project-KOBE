"""MuteMe Mini physical button integration (Phase 6).

Runs alongside `mute/service.py`'s keyboard hotkey — both services publish
`MuteToggled` to the bus, and we mirror each other's state on the LED. A
fingertip-tap on the USB button toggles mute just like `ctrl+alt+k` does.

Protocol (confirmed from MuteMe docs + firmware teardown notes):
  - Generic HID, no admin / no driver.
  - Input report is a single byte:
      0x00 idle, 0x01 touching, 0x02 end-touch, 0x04 start-touch.
  - LED is driven by a single-byte **feature report** (prepend report id 0):
      colors       0x01 red, 0x02 green, 0x03 yellow, 0x04 blue,
                   0x05 purple, 0x06 cyan, 0x07 white
      +0x10 dim, +0x20 fast pulse, +0x30 slow pulse; 0x00 clears.

We deliberately use a **blocking** `device.read(..., timeout_ms=...)` in a
background thread rather than busy-polling: the MuteMe only emits on state
change, so `read` returns promptly on press and otherwise sleeps kernel-side.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import InterruptRequested, MuteToggled

log = structlog.get_logger(__name__)

# VID/PID pairs across the MuteMe Mini product line. Enumerate rather than
# hardcoding one — the same firmware ships under multiple USB IDs depending
# on connector (USB-A / USB-C) and production batch.
MUTEME_IDS: tuple[tuple[int, int], ...] = (
    (0x20A0, 0x42DB),  # production
    (0x3603, 0x0002),  # USB-C revision
    (0x3603, 0x0003),  # USB-A revision
    (0x3603, 0x0004),  # generic
)

# LED feature-report bytes.
LED_OFF = 0x00
LED_RED_SOLID = 0x01           # muted
LED_CYAN_SLOW_PULSE = 0x36     # 0x30 slow-pulse + 0x06 cyan = "ready / unmuted"

# Input report codes.
EVT_IDLE = 0x00
EVT_TOUCH = 0x01
EVT_RELEASE = 0x02
EVT_TOUCH_START = 0x04


def _find_device_info(hid_mod: Any) -> dict[str, Any] | None:
    """Return the best matching MuteMe enumeration record, or None.

    Some MuteMe revisions expose multiple HID interfaces (e.g. an input
    interface for the button and a separate output interface for the LED).
    If we blindly open the first enumerated record we can end up on an
    interface that never delivers button events, so the service looks
    connected but is silent.

    Selection strategy:
      1. Collect every record whose `(vendor_id, product_id)` matches one of
         our four known MuteMe pairs.
      2. Prefer records whose `usage_page` suggests input-capable HID —
         Consumer (0x0C), Generic Desktop (0x01), or a vendor-specific range
         (>= 0xFF00) — since MuteMe publishes its button under a vendor page.
         Records with `usage_page == 0` (interface-only, no reports) are
         deprioritised.
      3. Within the preferred bucket, pick the record with the LOWEST
         `interface_number` (0 if unset) — empirically the primary interface.
      4. Fall back to the first record if nothing matches preference.
    """
    try:
        entries = hid_mod.enumerate()
    except Exception as exc:  # noqa: BLE001
        log.warning("muteme_enumerate_failed", error=str(exc))
        return None
    wanted = set(MUTEME_IDS)
    candidates: list[dict[str, Any]] = []
    for info in entries:
        try:
            vid = int(info.get("vendor_id", 0))
            pid = int(info.get("product_id", 0))
        except (TypeError, ValueError):
            continue
        if (vid, pid) in wanted:
            candidates.append(info)
    if not candidates:
        return None

    def _score(info: dict[str, Any]) -> tuple[int, int]:
        # Lower tuple wins.
        try:
            usage_page = int(info.get("usage_page", 0) or 0)
        except (TypeError, ValueError):
            usage_page = 0
        try:
            iface = int(info.get("interface_number", 0) or 0)
        except (TypeError, ValueError):
            iface = 0
        # Bucket: 0 = likely-input, 1 = unknown, 2 = interface-only.
        if usage_page in (0x01, 0x0C) or usage_page >= 0xFF00:
            bucket = 0
        elif usage_page == 0:
            bucket = 2
        else:
            bucket = 1
        return (bucket, iface)

    candidates.sort(key=_score)
    return candidates[0]


def _send_led(device: Any, value: int) -> None:
    """Best-effort LED update via HID feature report. Never raises."""
    try:
        device.send_feature_report([0, value & 0xFF])
    except Exception as exc:  # noqa: BLE001
        log.debug("muteme_led_failed", value=hex(value), error=str(exc))


async def run_muteme_service(bus: Bus, settings: Settings) -> None:
    """Long-running coroutine: watches the MuteMe Mini and publishes MuteToggled."""
    if not settings.muteme_enabled:
        log.info("muteme_disabled")
        return

    try:
        import hid  # type: ignore[import-not-found]
    except ImportError as exc:
        log.info(
            "muteme_unavailable_import",
            error=str(exc),
            hint="install `hidapi>=0.14` to enable the physical mute button",
        )
        return

    info = _find_device_info(hid)
    if info is None:
        # Common case when the button just isn't plugged in — keep at INFO so
        # the default log stream stays quiet but the state is still visible.
        log.info("muteme_not_connected", scanned_ids=[(hex(v), hex(p)) for v, p in MUTEME_IDS])
        return

    vid = int(info.get("vendor_id", 0))
    pid = int(info.get("product_id", 0))
    path = info.get("path")

    device: Any
    try:
        device = hid.device()
        # Prefer path-based open when available — some MuteMe revisions expose
        # multiple HID interfaces (LED vs. button) under the same VID/PID.
        if path:
            device.open_path(path)
        else:
            device.open(vid, pid)
        try:
            device.set_nonblocking(False)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        log.warning("muteme_open_failed", vid=hex(vid), pid=hex(pid), error=str(exc))
        return

    log.info("muteme_connected", vid=hex(vid), pid=hex(pid))

    # Startup indicator: slow-pulse cyan == "ready, not muted".
    _send_led(device, LED_CYAN_SLOW_PULSE)

    loop = asyncio.get_running_loop()
    toggle_event = asyncio.Event()
    stop_flag = threading.Event()

    # --- HID reader thread --------------------------------------------------
    def _reader() -> None:
        poll_ms = max(1, int(settings.muteme_poll_ms))
        while not stop_flag.is_set():
            try:
                data = device.read(8, timeout_ms=poll_ms)
            except Exception as exc:  # noqa: BLE001
                # Device yanked / USB stack hiccup — mark the service dead
                # FIRST so the async side doesn't treat the wake as a press.
                log.warning("muteme_read_failed", error=str(exc))
                stop_flag.set()
                loop.call_soon_threadsafe(toggle_event.set)
                return
            if not data:
                continue
            code = data[0]
            if code == EVT_TOUCH_START:
                # Only the rising edge counts as "one press = one toggle".
                loop.call_soon_threadsafe(toggle_event.set)
            # EVT_TOUCH (held) and EVT_RELEASE are intentionally ignored.

    reader = threading.Thread(target=_reader, name="muteme-reader", daemon=True)
    reader.start()

    # --- Bus mirror subscription -------------------------------------------
    # If the keyboard hotkey (or any other publisher) flips mute, mirror it.
    mute_queue = bus.subscribe(MuteToggled)

    # Idempotent mirror: if an incoming MuteToggled matches our current
    # state, we no-op. That correctly swallows our own echoes without any
    # fragile last-published tracking and survives rapid back-to-back toggles.
    muted = False
    last_led = LED_CYAN_SLOW_PULSE

    async def _apply_led(value: int) -> None:
        nonlocal last_led
        if value == last_led:
            return
        last_led = value
        # LED writes are nice-to-have — a device unplug or USB stack hiccup
        # after startup must NOT tear down the TaskGroup. Mirror the
        # best-effort semantics of `_send_led` used for the startup write.
        try:
            await asyncio.to_thread(device.send_feature_report, [0, value & 0xFF])
        except Exception as exc:  # noqa: BLE001
            log.debug("muteme_led_apply_failed", value=hex(value), error=str(exc))

    async def _mirror_bus() -> None:
        nonlocal muted
        while True:
            evt = await mute_queue.get()
            # Idempotent: if the bus already agrees with our local state,
            # this is either our own echo or a redundant publish — either
            # way there's nothing to do. No LED rewrite, no republish.
            if evt.muted == muted:
                continue
            muted = evt.muted
            log.info("muteme_mirror_bus", muted=muted)
            await _apply_led(LED_RED_SOLID if muted else LED_CYAN_SLOW_PULSE)

    mirror_task = asyncio.create_task(_mirror_bus(), name="muteme-mirror")

    log.info("muteme_service_start", poll_ms=settings.muteme_poll_ms)

    try:
        while True:
            await toggle_event.wait()
            toggle_event.clear()
            if stop_flag.is_set():
                break
            muted = not muted
            log.info("muteme_toggled", muted=muted)
            await bus.publish(MuteToggled(muted=muted))
            if muted:
                await bus.publish(InterruptRequested(reason="muteme"))
            await _apply_led(LED_RED_SOLID if muted else LED_CYAN_SLOW_PULSE)
    except asyncio.CancelledError:
        log.info("muteme_service_stop")
        raise
    finally:
        stop_flag.set()
        mirror_task.cancel()
        try:
            await mirror_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        bus.unsubscribe(MuteToggled, mute_queue)
        # Join reader thread with a bounded timeout so shutdown can't hang.
        reader.join(timeout=2.0)
        if reader.is_alive():
            log.warning("muteme_reader_join_timeout")
        # Clear the LED so the button goes dark on exit.
        try:
            await asyncio.to_thread(device.send_feature_report, [0, LED_OFF])
        except Exception as exc:  # noqa: BLE001
            log.debug("muteme_led_reset_failed", error=str(exc))
        try:
            device.close()
        except Exception as exc:  # noqa: BLE001
            log.debug("muteme_close_failed", error=str(exc))
        log.info("muteme_service_clean")
