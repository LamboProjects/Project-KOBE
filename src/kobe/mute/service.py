"""Mute service — global hotkey toggle that publishes MuteToggled events.

Uses the synchronous `keyboard` module, which installs a low-level hook on
Windows. On some systems this requires the process to run with administrator
privileges; if registration fails we log a warning and exit cleanly rather than
taking down the whole pipeline.

Also publishes `InterruptRequested` on each mute-to-true transition so any TTS
currently speaking shuts up immediately.

# TODO(Phase 6): wire up a physical mute button via MuteMe Mini (USB HID).
# Detect device on startup, mirror its LED to `self._muted`, and treat button
# presses as additional toggle sources alongside the keyboard hotkey.
"""
from __future__ import annotations

import asyncio

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import InterruptRequested, MuteToggled

log = structlog.get_logger(__name__)


async def run_mute_service(bus: Bus, settings: Settings) -> None:
    """Long-running coroutine: listens for the mute hotkey and publishes MuteToggled."""
    try:
        import keyboard  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "mute_service_unavailable_import",
            error=str(exc),
            hint="install the `keyboard` package or live without the hotkey",
        )
        return

    loop = asyncio.get_running_loop()
    toggle_event = asyncio.Event()

    def _on_hotkey() -> None:
        # Called from the `keyboard` library's internal thread. Hop back to
        # the asyncio loop via a threadsafe set().
        loop.call_soon_threadsafe(toggle_event.set)

    hotkey_handle: object | None = None
    try:
        # `add_hotkey` returns a handle we can use for a scoped removal
        # on shutdown (prefer this over remove_all_hotkeys, which would
        # clobber any other in-process registrations).
        hotkey_handle = await asyncio.to_thread(
            keyboard.add_hotkey, settings.mute_hotkey, _on_hotkey
        )
    except Exception as exc:  # noqa: BLE001
        # Typical cause on Windows: requires admin to install the low-level hook.
        log.warning(
            "mute_hotkey_register_failed",
            hotkey=settings.mute_hotkey,
            error=str(exc),
            hint="keyboard module may require admin privileges",
        )
        return

    muted = False
    log.info("mute_service_start", hotkey=settings.mute_hotkey)

    try:
        while True:
            await toggle_event.wait()
            toggle_event.clear()
            muted = not muted
            log.info("mute_toggled", muted=muted)
            await bus.publish(MuteToggled(muted=muted))
            if muted:
                # Muting should also silence ongoing TTS — otherwise "mute"
                # feels broken when KOBE is mid-sentence.
                await bus.publish(InterruptRequested(reason="muted"))
    except asyncio.CancelledError:
        log.info("mute_service_stop")
        raise
    finally:
        # Some `keyboard` versions return `None` from `add_hotkey` even on
        # success, so the hotkey gets registered but our handle is None and
        # a handle-based remove would leak the OS-level low-level hook
        # across dev restarts. Fall back to removing by hotkey string when
        # the handle is missing.
        try:
            if hotkey_handle is not None:
                await asyncio.to_thread(keyboard.remove_hotkey, hotkey_handle)
            else:
                await asyncio.to_thread(keyboard.remove_hotkey, settings.mute_hotkey)
        except Exception as exc:  # noqa: BLE001
            log.warning("mute_hotkey_cleanup_failed", error=str(exc))
