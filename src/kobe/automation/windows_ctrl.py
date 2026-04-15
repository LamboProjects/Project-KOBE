"""Windows OS automation service for Project KOBE.

Subscribes to `ActionRequested` and handles OS-level voice intents:
  - Master volume: set / up / down / mute / unmute (pycaw + COM)
  - Window: focus, minimize-all, minimize-active, maximize-active (pygetwindow / Win32)
  - Desktop: show_desktop (Windows+D)

pycaw/comtypes are lazily imported so missing deps degrade gracefully rather than
killing the whole service; volume intents fail with ok=False in that case.

All pycaw calls run through `asyncio.to_thread` because COM endpoint-volume
objects are apartment-threaded — binding them on the event loop thread and
calling across thread boundaries is fine as long as we always call from the
same worker thread. We take the simpler path of re-activating per call, which
is cheap and sidesteps any thread-affinity subtleties.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested

log = structlog.get_logger(__name__)


# ---------- volume (pycaw) ----------


def _load_pycaw() -> tuple[Any, Any, Any, Any] | None:
    """Lazy import of pycaw/comtypes. Returns (AudioUtilities, IAudioEndpointVolume,
    CLSCTX_ALL, cast_fn) or None if unavailable."""
    try:
        from ctypes import POINTER, cast  # noqa: WPS433
        from comtypes import CLSCTX_ALL  # noqa: WPS433
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # noqa: WPS433
    except Exception as exc:  # pragma: no cover - platform/dep dependent
        log.warning("pycaw_unavailable", error=str(exc))
        return None

    def _cast_to_endpoint(interface):
        return cast(interface, POINTER(IAudioEndpointVolume))

    return AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL, _cast_to_endpoint


def _get_endpoint_volume(pycaw_bundle):
    AudioUtilities, IAudioEndpointVolume, CLSCTX_ALL, _cast = pycaw_bundle
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return _cast(interface)


def _sync_set_volume(pycaw_bundle, level_0_to_1: float) -> float:
    vol = _get_endpoint_volume(pycaw_bundle)
    vol.SetMasterVolumeLevelScalar(float(level_0_to_1), None)
    return float(vol.GetMasterVolumeLevelScalar())


def _sync_get_volume(pycaw_bundle) -> float:
    vol = _get_endpoint_volume(pycaw_bundle)
    return float(vol.GetMasterVolumeLevelScalar())


def _sync_set_mute(pycaw_bundle, muted: bool) -> None:
    vol = _get_endpoint_volume(pycaw_bundle)
    vol.SetMute(1 if muted else 0, None)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


# ---------- handlers ----------


async def _handle_volume_set(pycaw_bundle, params: dict[str, Any]) -> tuple[bool, str]:
    if pycaw_bundle is None:
        return False, "pycaw unavailable"
    try:
        level = _clamp(int(params.get("level", 50)), 0, 100)
    except (TypeError, ValueError):
        return False, "invalid level"
    new_level = await asyncio.to_thread(_sync_set_volume, pycaw_bundle, level / 100.0)
    return True, f"volume={int(round(new_level * 100))}"


async def _handle_volume_step(
    pycaw_bundle, params: dict[str, Any], direction: int
) -> tuple[bool, str]:
    if pycaw_bundle is None:
        return False, "pycaw unavailable"
    try:
        step = _clamp(int(params.get("step", 10)), 1, 100)
    except (TypeError, ValueError):
        step = 10
    current = await asyncio.to_thread(_sync_get_volume, pycaw_bundle)
    target = _clamp(int(round(current * 100)) + direction * step, 0, 100)
    new_level = await asyncio.to_thread(_sync_set_volume, pycaw_bundle, target / 100.0)
    return True, f"volume={int(round(new_level * 100))}"


async def _handle_mute(pycaw_bundle, muted: bool) -> tuple[bool, str]:
    if pycaw_bundle is None:
        return False, "pycaw unavailable"
    await asyncio.to_thread(_sync_set_mute, pycaw_bundle, muted)
    return True, "muted" if muted else "unmuted"


def _sync_focus_window(substr: str) -> tuple[bool, str]:
    try:
        import pygetwindow as gw  # noqa: WPS433
    except Exception as exc:
        return False, f"pygetwindow unavailable: {exc}"
    needle = substr.lower()
    matches = [
        w for w in gw.getAllWindows()
        if (w.title or "") and needle in w.title.lower()
    ]
    matches = [w for w in matches if (w.title or "").strip()]
    if not matches:
        return False, f"no window matching {substr!r}"
    win = matches[0]
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception as exc:  # pygetwindow raises on some edge cases
        return False, f"activate failed: {exc}"
    return True, f"focused {win.title!r}"


def _sync_minimize_all() -> tuple[bool, str]:
    try:
        import pygetwindow as gw  # noqa: WPS433
    except Exception as exc:
        return False, f"pygetwindow unavailable: {exc}"
    count = 0
    for w in gw.getAllWindows():
        if not (w.title or "").strip():
            continue
        try:
            if w.visible and not w.isMinimized:
                w.minimize()
                count += 1
        except Exception:
            continue
    return True, f"minimized {count} windows"


def _sync_active_window_op(op: str) -> tuple[bool, str]:
    try:
        import pygetwindow as gw  # noqa: WPS433
    except Exception as exc:
        return False, f"pygetwindow unavailable: {exc}"
    win = gw.getActiveWindow()
    if win is None:
        return False, "no active window"
    try:
        if op == "minimize":
            win.minimize()
        elif op == "maximize":
            win.maximize()
        else:
            return False, f"unknown op {op}"
    except Exception as exc:
        return False, f"{op} failed: {exc}"
    return True, f"{op} {win.title!r}"


def _sync_show_desktop() -> tuple[bool, str]:
    try:
        import keyboard  # noqa: WPS433
    except Exception as exc:
        return False, f"keyboard unavailable: {exc}"
    try:
        keyboard.send("windows+d")
    except Exception as exc:
        return False, f"show_desktop failed: {exc}"
    return True, "show_desktop"


# ---------- service ----------


async def run_windows_automation_service(bus: Bus, settings: Settings) -> None:
    """Long-running service: consume ActionRequested and drive Windows OS."""
    _ = settings  # no config knobs yet
    pycaw_bundle = await asyncio.to_thread(_load_pycaw)
    if pycaw_bundle is None:
        log.warning("windows_automation_degraded", reason="pycaw import failed")
    else:
        log.info("windows_automation_ready")

    queue = bus.subscribe(ActionRequested)
    try:
        while True:
            try:
                evt: ActionRequested = await queue.get()
            except asyncio.CancelledError:
                raise

            action = evt.action
            params = evt.params or {}
            ok: bool | None = None
            detail: str = ""

            try:
                if action == "volume_set":
                    ok, detail = await _handle_volume_set(pycaw_bundle, params)
                elif action == "volume_up":
                    ok, detail = await _handle_volume_step(pycaw_bundle, params, +1)
                elif action == "volume_down":
                    ok, detail = await _handle_volume_step(pycaw_bundle, params, -1)
                elif action == "volume_mute":
                    ok, detail = await _handle_mute(pycaw_bundle, True)
                elif action == "volume_unmute":
                    ok, detail = await _handle_mute(pycaw_bundle, False)
                elif action == "window_focus":
                    substr = str(params.get("title_contains", "")).strip()
                    if not substr:
                        ok, detail = False, "title_contains required"
                    else:
                        ok, detail = await asyncio.to_thread(_sync_focus_window, substr)
                elif action == "window_minimize_all":
                    ok, detail = await asyncio.to_thread(_sync_minimize_all)
                elif action == "window_minimize_active":
                    ok, detail = await asyncio.to_thread(_sync_active_window_op, "minimize")
                elif action == "window_maximize_active":
                    ok, detail = await asyncio.to_thread(_sync_active_window_op, "maximize")
                elif action == "show_desktop":
                    ok, detail = await asyncio.to_thread(_sync_show_desktop)
                else:
                    # Not ours — let other executors handle it.
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("action_failed", action=action)
                ok, detail = False, f"error: {exc}"

            if ok is None:
                continue

            log.info("action_completed", action=action, ok=ok, detail=detail)
            await bus.publish(
                ActionCompleted(
                    request_id=evt.request_id,
                    action=action,
                    ok=ok,
                    detail=detail,
                )
            )
    except asyncio.CancelledError:
        log.info("windows_automation_cancelled")
        raise
    finally:
        bus.unsubscribe(ActionRequested, queue)
