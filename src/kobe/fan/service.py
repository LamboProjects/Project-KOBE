"""Asyncio service that drives the holographic fan (Phase 7).

Fans-in three event streams (`PrinterStatus`, `NowPlayingChanged`,
`GestureDetected`) into a single internal work queue. A worker re-evaluates
the "mode" (gesture flash > printer progress > spotify > idle logo),
renders the clip off the loop thread via `asyncio.to_thread`, and hands it
to the fan backend. A scene-hash makes sure we only push when the scene
changed; a monotonic cooldown rate-limits pushes to the device.

Auxiliary tasks: idle timer (logo/STL refresh) and telemetry (10 s health
pulses). Never raises into the bus.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    FanBackendStatus,
    FanClipPushed,
    GestureDetected,
    NowPlayingChanged,
    PrinterStatus,
)

log = structlog.get_logger(__name__)

_TELEMETRY_INTERVAL_S = 10.0
_PRINTER_ACTIVE_STAGES: frozenset[str] = frozenset({"printing", "paused"})
_PRINTER_RECENT_WINDOW_S = 30.0
_WORK_QUEUE_MAXSIZE = 32


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _State:
    last_printer: PrinterStatus | None = None
    last_printer_mono: float = 0.0
    last_now_playing: NowPlayingChanged | None = None
    last_gesture: GestureDetected | None = None
    last_gesture_mono: float = 0.0
    idle_toggle: bool = False
    last_pushed_hash: tuple | None = None
    last_push_mono: float = 0.0


def _printer_bucket(pct: float) -> int:
    try:
        return int(max(0.0, min(100.0, float(pct))) // 5)
    except (TypeError, ValueError):
        return 0


def _pick_scene(
    state: _State, settings: Settings, now_mono: float
) -> tuple[str, tuple, dict[str, Any]]:
    """Return (mode, dedup_hash, render_kwargs). Priority:
    gesture flash > printer > spotify > idle logo/STL."""
    # 1. Gesture flash — preempts everything within the flash window.
    g = state.last_gesture
    if g is not None and (now_mono - state.last_gesture_mono) <= float(
        settings.hologram_gesture_flash_s
    ):
        return (
            "gesture",
            ("gesture", g.name, g.timestamp_iso),
            {"gesture": g.name, "seconds": float(settings.hologram_gesture_flash_s)},
        )

    # 2. Printer progress — active stage OR recent status within window.
    ps = state.last_printer
    if ps is not None and (
        ps.stage in _PRINTER_ACTIVE_STAGES
        or (now_mono - state.last_printer_mono) <= _PRINTER_RECENT_WINDOW_S
    ):
        return (
            "printer",
            ("printer", ps.stage, _printer_bucket(ps.progress_pct), ps.filename),
            {"pct": float(ps.progress_pct), "stage": ps.stage, "filename": ps.filename},
        )

    # 3. Spotify now-playing.
    np = state.last_now_playing
    if np is not None and np.is_playing:
        return (
            "spotify",
            ("spotify", np.track, np.artist, True),
            {"is_playing": True, "track": np.track, "artist": np.artist},
        )

    # 4. Idle logo / STL alternation.
    refresh_s = max(1.0, float(settings.hologram_logo_refresh_s))
    stl_path = (settings.hologram_stl_path or "").strip()
    if stl_path and state.idle_toggle:
        return (
            "stl",
            ("stl", stl_path, int(now_mono // refresh_s)),
            {"stl_path": stl_path, "seconds": refresh_s},
        )
    return (
        "logo",
        ("logo", int(now_mono // refresh_s)),
        {"text": "KOBE", "seconds": refresh_s},
    )


async def _render(content_mod: Any, settings: Settings, mode: str, kwargs: dict[str, Any]):
    """Dispatch to the right renderer off the loop thread.
    Returns `(path, duration_s)` or `None` when the renderer yields nothing.

    NOTE: every `content.render_*` function is keyword-only after `settings`.
    We wrap in functools.partial so `asyncio.to_thread` can pass them through
    unchanged — positional passthrough would TypeError at every render.
    """
    from functools import partial

    if mode == "gesture":
        path = await asyncio.to_thread(
            partial(content_mod.render_gesture_flash, settings,
                    gesture=kwargs["gesture"], seconds=kwargs["seconds"])
        )
        return path, float(kwargs["seconds"])
    if mode == "printer":
        path = await asyncio.to_thread(
            partial(content_mod.render_progress_ring, settings,
                    pct=kwargs["pct"], stage=kwargs["stage"], filename=kwargs["filename"])
        )
        return path, float(settings.hologram_logo_refresh_s)
    if mode == "spotify":
        path = await asyncio.to_thread(
            partial(content_mod.render_spotify_waveform, settings,
                    is_playing=kwargs["is_playing"],
                    track=kwargs["track"], artist=kwargs["artist"])
        )
        return path, float(settings.hologram_logo_refresh_s)
    if mode == "stl":
        path = await asyncio.to_thread(
            partial(content_mod.render_stl_rotation, settings,
                    stl_path=kwargs["stl_path"], seconds=kwargs["seconds"])
        )
        if path is None:
            return None
        return path, float(kwargs["seconds"])
    path = await asyncio.to_thread(
        partial(content_mod.render_rotating_logo, settings,
                text=kwargs["text"], seconds=kwargs["seconds"])
    )
    return path, float(kwargs["seconds"])


async def _safe_publish_health(bus: Bus, backend: Any, backend_name: str) -> None:
    try:
        health = await backend.health()
        await bus.publish(
            FanBackendStatus(
                # BackendHealth exposes `name` (matches the backend's own
                # `name` attr). Prefer that; fall back to the caller-supplied
                # name only if somehow absent.
                backend=str(getattr(health, "name", backend_name) or backend_name),
                connected=bool(getattr(health, "connected", False)),
                detail=str(getattr(health, "detail", "") or ""),
                timestamp_iso=_now_iso(),
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("fan_health_failed", error=str(exc))


async def run_fan_service(bus: Bus, settings: Settings) -> None:
    # --- 1. Disabled / dependency checks --------------------------------
    if settings.hologram_enabled is False:
        log.info("fan_disabled")
        return

    try:
        from kobe.fan import content as content_mod  # type: ignore
        from kobe.fan import driver as driver_mod  # type: ignore
    except ImportError as exc:
        log.warning("fan_unavailable_import", error=str(exc))
        return

    # Probe the heavy render dependencies up-front. On a default `uv sync`
    # (no `--extra hologram`), `imageio` / `trimesh` are missing but the
    # thin `kobe.fan.content` module still imports cleanly because the
    # renderers lazy-import them. If we skipped this check, every scene
    # would fail inside the worker and spam `fan_render_failed` warnings.
    # Disable cleanly instead — the rest of the pipeline keeps working.
    try:
        import imageio  # noqa: F401
    except ImportError as exc:
        log.info(
            "fan_hologram_extra_missing",
            error=str(exc),
            hint="install with `uv sync --extra hologram` to enable fan output",
        )
        return

    try:
        backend = driver_mod.build_backend(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("fan_backend_build_failed", error=str(exc))
        return

    backend_name = getattr(backend, "name", settings.hologram_backend)
    log.info("fan_service_started", backend=backend_name)
    await _safe_publish_health(bus, backend, backend_name)

    printer_q = bus.subscribe(PrinterStatus)
    now_playing_q = bus.subscribe(NowPlayingChanged)
    gesture_q = bus.subscribe(GestureDetected)

    state = _State()
    work: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=_WORK_QUEUE_MAXSIZE)

    # --- 2. Fan-in tasks ------------------------------------------------
    async def _fanin(src_q: "asyncio.Queue[Any]", kind: str, tag: str) -> None:
        while True:
            ev = await src_q.get()
            # Drop-oldest on overflow: one stuck producer shouldn't wedge the
            # whole TaskGroup. Mirrors `Bus.publish`'s overflow strategy.
            try:
                work.put_nowait((kind, ev))
            except asyncio.QueueFull:
                try:
                    work.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    work.put_nowait((kind, ev))
                except asyncio.QueueFull:
                    log.warning(f"fan_fanin_{tag}_drop", reason="queue_full_twice")

    # --- 3. Worker ------------------------------------------------------
    async def _maybe_push(now_mono: float) -> None:
        try:
            mode, scene_hash, kwargs = _pick_scene(state, settings, now_mono)
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_pick_scene_failed", error=str(exc))
            return
        if scene_hash == state.last_pushed_hash:
            return
        cooldown = float(settings.hologram_clip_cooldown_s)
        if (
            state.last_push_mono > 0.0
            and (now_mono - state.last_push_mono) < cooldown
            and mode != "gesture"  # gesture flashes preempt cooldown
        ):
            log.debug("fan_push_cooldown_skip", mode=mode)
            return
        try:
            rendered = await _render(content_mod, settings, mode, kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_render_failed", mode=mode, error=str(exc))
            return
        if rendered is None:
            log.debug("fan_render_skipped", mode=mode)
            return
        path, duration_s = rendered
        try:
            pushed = await backend.push_clip(
                path=path, name=mode, duration_s=duration_s, loop=(mode != "gesture")
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_push_failed", mode=mode, error=str(exc))
            return
        if not pushed:
            # Backend reported failure — don't advance `last_pushed_hash` or
            # emit `FanClipPushed`. If we did, the same scene would be
            # silently stuck (hash dedup blocks retry) until something else
            # changes the scene.
            log.info("fan_push_rejected", mode=mode)
            return
        state.last_pushed_hash = scene_hash
        state.last_push_mono = now_mono
        log.info("fan_clip_pushed", mode=mode, duration_s=round(duration_s, 2))
        try:
            await bus.publish(
                FanClipPushed(
                    name=mode,
                    duration_s=float(duration_s),
                    path="",  # never leak server-local path to HUD/WS
                    timestamp_iso=_now_iso(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_publish_pushed_failed", error=str(exc))

    async def _worker() -> None:
        while True:
            kind, payload = await work.get()
            now_mono = time.monotonic()
            try:
                if kind == "printer" and isinstance(payload, PrinterStatus):
                    state.last_printer = payload
                    state.last_printer_mono = now_mono
                elif kind == "spotify" and isinstance(payload, NowPlayingChanged):
                    state.last_now_playing = payload
                elif kind == "gesture" and isinstance(payload, GestureDetected):
                    state.last_gesture = payload
                    state.last_gesture_mono = now_mono
                elif kind == "idle":
                    state.idle_toggle = not state.idle_toggle
            except Exception as exc:  # noqa: BLE001
                log.warning("fan_state_update_failed", error=str(exc))
                continue
            await _maybe_push(now_mono)

    # --- 4. Idle timer + telemetry --------------------------------------
    async def _idle_timer() -> None:
        interval = max(1.0, float(settings.hologram_logo_refresh_s))
        # Seed an initial idle tick immediately so the fan gets a logo clip
        # within the first second instead of waiting a full refresh period
        # (60 s by default) before anything shows up.
        try:
            work.put_nowait(("idle", None))
        except asyncio.QueueFull:
            pass
        while True:
            await asyncio.sleep(interval)
            try:
                await work.put(("idle", None))
            except Exception as exc:  # noqa: BLE001
                log.warning("fan_idle_enqueue_failed", error=str(exc))

    async def _telemetry() -> None:
        while True:
            await asyncio.sleep(_TELEMETRY_INTERVAL_S)
            await _safe_publish_health(bus, backend, backend_name)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_fanin(printer_q, "printer", "printer"), name="fan-printer-fanin")
            tg.create_task(_fanin(now_playing_q, "spotify", "spotify"), name="fan-spotify-fanin")
            tg.create_task(_fanin(gesture_q, "gesture", "gesture"), name="fan-gesture-fanin")
            tg.create_task(_worker(), name="fan-worker")
            tg.create_task(_idle_timer(), name="fan-idle-timer")
            tg.create_task(_telemetry(), name="fan-telemetry")
    except* asyncio.CancelledError:
        raise
    except* Exception as eg:  # noqa: BLE001
        for exc in eg.exceptions:
            log.warning("fan_task_failed", error=str(exc))
    finally:
        # --- 5. Shutdown -------------------------------------------------
        try:
            await backend.clear()
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_clear_failed", error=str(exc))
        close = getattr(backend, "close", None)
        if close is not None:
            try:
                res = close()
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:  # noqa: BLE001
                log.warning("fan_close_failed", error=str(exc))
        try:
            await bus.publish(
                FanBackendStatus(
                    backend=backend_name, connected=False,
                    detail="shutdown", timestamp_iso=_now_iso(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_final_status_failed", error=str(exc))
        for et, q in (
            (PrinterStatus, printer_q),
            (NowPlayingChanged, now_playing_q),
            (GestureDetected, gesture_q),
        ):
            try:
                bus.unsubscribe(et, q)
            except Exception as exc:  # noqa: BLE001
                log.debug("fan_unsubscribe_failed", error=str(exc))
        log.info("fan_service_stopped")
