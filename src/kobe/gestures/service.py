"""Async gesture service (Phase 5).

Owns the `GestureCamera` + `GestureClassifier` lifecycle, bridges frame results
from the camera thread onto the asyncio loop via a bounded drop-oldest queue,
classifies them into semantic `GestureDetected` events, emits periodic
`WebcamStatus` telemetry, and optionally maps a handful of gestures to
`ActionRequested` events so the HUD can be navigated hands-free.

Fully tolerant of missing optional deps (mediapipe / opencv): if the gesture
subpackage can't import, the service logs and returns cleanly instead of
taking down the whole TaskGroup.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    ActionRequested,
    GestureDetected,
    MuteToggled,
    WebcamStatus,
)

log = structlog.get_logger(__name__)

# Fixed gesture -> HUD action map. Phase 5 success criterion: HUD panel
# navigation by gesture. A future phase can make this user-configurable via
# Settings (e.g. `gesture_action_map: dict[str, str]`).
_GESTURE_ACTION_MAP: dict[str, str] = {
    "swipe_left": "hud_navigate_prev",
    "swipe_right": "hud_navigate_next",
    "point": "hud_select",
    "confirm": "hud_confirm",
    "dismiss": "hud_dismiss",
}

_TELEMETRY_INTERVAL_S = 2.0
_FRAME_QUEUE_MAXSIZE = 64


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_put(q: "asyncio.Queue[Any]", item: Any) -> None:
    """Put `item` on `q`, dropping the oldest entry if full.

    Called from the loop via `call_soon_threadsafe`, so we never block the
    camera thread; mediapipe keeps delivering frames and a full queue just
    means the classifier is behind.
    """
    try:
        q.put_nowait(item)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            # Two consumers racing us — give up on this frame.
            pass


async def run_gesture_service(bus: Bus, settings: Settings) -> None:
    # --- 1. Disabled / dependency checks ---------------------------------
    if settings.gesture_enabled is False:
        log.info("gesture_disabled")
        return

    try:
        from kobe.gestures.camera import GestureCamera, ensure_model  # type: ignore
        from kobe.gestures.classifier import GestureClassifier  # type: ignore
    except Exception as exc:  # noqa: BLE001 - any import failure
        log.warning("gesture_unavailable_import", error=str(exc))
        return

    try:
        await ensure_model(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("gesture_model_unavailable", error=str(exc))
        return

    # --- 2. Wire up ------------------------------------------------------
    classifier = GestureClassifier(settings)
    loop = asyncio.get_running_loop()
    frame_q: asyncio.Queue[Any] = asyncio.Queue(maxsize=_FRAME_QUEUE_MAXSIZE)

    def on_result(fr: Any) -> None:
        # Camera marshals sync `on_result` callbacks onto the asyncio loop
        # via `loop.call_soon_threadsafe(on_result, fr)` already, so by the
        # time we run we're ON the loop thread — calling
        # `call_soon_threadsafe` again would just schedule a deferred
        # `_safe_put` and grow MediaPipe's pending-callback queue past the
        # 64-frame backpressure limit `frame_q` is supposed to enforce.
        # Put directly so drop-oldest actually engages under load.
        _safe_put(frame_q, fr)

    try:
        camera = GestureCamera(settings, on_result=on_result, loop=loop)
    except Exception as exc:  # noqa: BLE001
        log.warning("gesture_camera_construct_failed", error=str(exc))
        return

    try:
        await asyncio.to_thread(camera.start)
    except Exception as exc:  # noqa: BLE001
        log.warning("gesture_camera_start_failed", error=str(exc))
        return

    log.info(
        "gesture_service_started",
        camera_index=settings.gesture_camera_index,
        resolution=f"{settings.gesture_camera_width}x{settings.gesture_camera_height}",
        fps=settings.gesture_camera_fps,
    )

    # --- 3. Mute integration --------------------------------------------
    mute_q = bus.subscribe(MuteToggled)
    muted_state = {"muted": False}

    # --- 4. Main loop ----------------------------------------------------
    async def classify_loop() -> None:
        while True:
            fr = await frame_q.get()
            if muted_state["muted"]:
                # Drop this frame AND drain anything that piled up while muted —
                # otherwise on unmute we'd flush stale frames through the
                # classifier and could emit a gesture the user made during the
                # muted window. The classifier's own state is also reset on
                # mute toggles in `mute_loop`.
                while not frame_q.empty():
                    try:
                        frame_q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                continue
            try:
                events = classifier.push(fr)
            except Exception as exc:  # noqa: BLE001
                log.warning("gesture_classify_failed", error=str(exc))
                continue
            for ev in events or ():
                try:
                    gd = GestureDetected(
                        name=ev.name,
                        confidence=ev.confidence,
                        hand=ev.hand,
                        raw_label=ev.raw_label,
                        timestamp_iso=_now_iso(),
                    )
                    await bus.publish(gd)
                    log.info(
                        "gesture_emitted",
                        name=ev.name,
                        confidence=round(float(ev.confidence), 3),
                        hand=ev.hand,
                        raw_label=ev.raw_label,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("gesture_publish_failed", error=str(exc))
                    continue

                # Optional gesture -> HUD action translation.
                action_name = _GESTURE_ACTION_MAP.get(ev.name)
                if action_name is not None:
                    try:
                        await bus.publish(
                            ActionRequested(
                                request_id=uuid4().hex[:12],
                                action=action_name,
                                params={},
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "gesture_action_publish_failed",
                            action=action_name,
                            error=str(exc),
                        )

    async def telemetry_loop() -> None:
        while True:
            try:
                status = camera.stats()
                await bus.publish(status)
            except Exception as exc:  # noqa: BLE001
                log.warning("gesture_stats_failed", error=str(exc))
            await asyncio.sleep(_TELEMETRY_INTERVAL_S)

    async def mute_loop() -> None:
        while True:
            ev = await mute_q.get()
            new_muted = bool(ev.muted)
            if new_muted != muted_state["muted"]:
                muted_state["muted"] = new_muted
                # Reset classifier on every transition so stale sliding-window
                # state (last N labels, palm motion buffer, etc.) can't fire
                # spurious gestures when we resume detection.
                try:
                    classifier.reset()
                    log.info(
                        "gesture_classifier_reset_for_mute",
                        muted=new_muted,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "gesture_classifier_reset_failed",
                        error=str(exc),
                    )
                log.info("gesture_mute_toggled", muted=muted_state["muted"])

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(classify_loop(), name="gesture-classify")
            tg.create_task(telemetry_loop(), name="gesture-telemetry")
            tg.create_task(mute_loop(), name="gesture-mute")
    except* asyncio.CancelledError:
        # Propagate cancellation after running shutdown in `finally`.
        raise
    except* Exception as eg:  # noqa: BLE001
        # Unexpected internal failure inside the task group — log but don't
        # propagate so the root TaskGroup stays alive for the other services.
        for exc in eg.exceptions:
            log.warning("gesture_task_failed", error=str(exc))
    finally:
        # --- 6. Shutdown -------------------------------------------------
        try:
            if camera.is_running:
                stats = camera.stats()
                frame_count = int(getattr(stats, "frame_count", 0) or 0)
            else:
                frame_count = 0
            final_status = WebcamStatus(
                connected=False,
                fps=0.0,
                frame_count=frame_count,
                detail="shutdown",
                timestamp_iso=_now_iso(),
            )
            await bus.publish(final_status)
        except Exception as exc:  # noqa: BLE001
            log.warning("gesture_final_status_failed", error=str(exc))

        try:
            await asyncio.to_thread(camera.stop)
        except Exception as exc:  # noqa: BLE001
            log.warning("gesture_camera_stop_failed", error=str(exc))

        try:
            bus.unsubscribe(MuteToggled, mute_q)
        except Exception as exc:  # noqa: BLE001
            log.debug("gesture_unsubscribe_failed", error=str(exc))

        log.info("gesture_service_stopped")
