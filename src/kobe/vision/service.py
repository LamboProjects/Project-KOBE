"""Screen vision service.

Two ways to ask for a screenshot analysis:

  1. Publish a `VisionRequested` on the bus — full control, includes region mode.
  2. Emit an `ActionRequested(action="screen_inspect", params=...)` from the brain.
     The service translates those into a `VisionRequested` internally so the
     action namespace stays consistent with the rest of KOBE (Phase 3 pattern).

Flow:
  VisionRequested  → capture via mss           (off the event loop)
                   → backend.analyse(...)      (backend decides)
                   → VisionResult              (for HUD + logging)
                   → ResponseReady             (so TTS speaks the answer)
                   → ActionCompleted           (when the trigger was an action)

Foundation-only: the default backend is the `NullBackend` stub that describes
the screenshot without calling any model. Real vision backends land later.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    ActionCompleted,
    ActionRequested,
    ResponseReady,
    VisionRequested,
    VisionResult,
)
from kobe.vision import capture as capture_mod
from kobe.vision.backends import build_backend, VisionBackend

log = structlog.get_logger(__name__)

_OWNED_ACTIONS: frozenset[str] = frozenset({"screen_inspect"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_mode(raw: Any) -> str:
    mode = str(raw or "foreground").strip().lower()
    if mode not in ("foreground", "full", "region"):
        return "foreground"
    return mode


def _coerce_region(raw: Any) -> tuple[int, int, int, int] | None:
    """Accept `[x,y,w,h]` / `(x,y,w,h)` / `{"x":..,"y":..,"w":..,"h":..}`."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            return (int(raw["x"]), int(raw["y"]), int(raw["w"]), int(raw["h"]))
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
        except (TypeError, ValueError):
            return None
    return None


async def _run_once(
    bus: Bus,
    settings: Settings,
    backend: VisionBackend,
    request_id: str,
    question: str,
    mode: str,
    region: tuple[int, int, int, int] | None,
) -> VisionResult:
    """Capture, analyse, publish. Returns the VisionResult so callers can also
    publish an ActionCompleted if the trigger was an action."""
    try:
        shot = await asyncio.wait_for(
            asyncio.to_thread(capture_mod.capture, mode, region),
            timeout=settings.vision_max_capture_seconds,
        )
    except asyncio.TimeoutError:
        log.warning("vision_capture_timeout", request_id=request_id, mode=mode)
        fail = VisionResult(
            request_id=request_id,
            ok=False,
            summary="Screen capture timed out.",
            width=0,
            height=0,
            backend=backend.name,
            timestamp_iso=_now_iso(),
        )
        await bus.publish(fail)
        await bus.publish(ResponseReady(request_id=request_id, text=fail.summary))
        return fail
    except Exception as exc:  # noqa: BLE001 - never crash the service
        log.exception("vision_capture_error", request_id=request_id, error=str(exc))
        fail = VisionResult(
            request_id=request_id,
            ok=False,
            summary=f"Screen capture failed: {exc}",
            width=0,
            height=0,
            backend=backend.name,
            timestamp_iso=_now_iso(),
        )
        await bus.publish(fail)
        await bus.publish(ResponseReady(request_id=request_id, text=fail.summary))
        return fail

    image_path = ""
    if settings.vision_save_screenshots:
        try:
            image_path = await asyncio.to_thread(
                capture_mod.save_png, shot, settings.vision_screenshot_dir
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("vision_save_failed", request_id=request_id, error=str(exc))

    try:
        summary = await backend.analyse(shot, question)
        ok = True
    except Exception as exc:  # noqa: BLE001 - backends promise not to raise,
        # but we defend in depth so TTS always has something to say.
        log.exception("vision_backend_error", backend=backend.name, error=str(exc))
        summary = f"Vision backend failed: {exc}"
        ok = False

    result = VisionResult(
        request_id=request_id,
        ok=ok,
        summary=summary,
        width=shot.width,
        height=shot.height,
        backend=backend.name,
        image_path=image_path,
        timestamp_iso=_now_iso(),
    )
    await bus.publish(result)
    await bus.publish(ResponseReady(request_id=request_id, text=summary))
    return result


async def run_vision_service(bus: Bus, settings: Settings) -> None:
    """Phase 4 foundation: serialises all screen-inspect work through one backend.

    We run two lightweight consumer tasks — one per trigger event type — that
    both push into a single internal work queue. A single worker drains that
    queue so captures are strictly sequential (two concurrent screen grabs
    would fight for GPU/network budget and surprise the user anyway).
    """
    if not settings.vision_enabled:
        log.info("vision_disabled")
        return

    backend = build_backend(settings)
    log.info("vision_service_started", backend=backend.name)

    vision_q = bus.subscribe(VisionRequested)
    action_q = bus.subscribe(ActionRequested)

    async def _from_vision_events(work: asyncio.Queue) -> None:
        while True:
            ev = await vision_q.get()
            await work.put(("vision", ev))

    async def _from_action_events(work: asyncio.Queue) -> None:
        while True:
            ev = await action_q.get()
            if ev.action in _OWNED_ACTIONS:
                await work.put(("action", ev))

    async def _worker(work: asyncio.Queue) -> None:
        while True:
            kind, ev = await work.get()
            if kind == "vision":
                try:
                    await _run_once(
                        bus,
                        settings,
                        backend,
                        ev.request_id,
                        ev.question,
                        _coerce_mode(ev.mode),
                        _coerce_region(ev.region),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception("vision_handler_crashed", error=str(exc))
            else:  # "action"
                params = ev.params or {}
                question = str(params.get("question", "") or params.get("prompt", ""))
                mode = _coerce_mode(params.get("mode"))
                region = _coerce_region(params.get("region"))
                try:
                    result = await _run_once(
                        bus, settings, backend, ev.request_id, question, mode, region
                    )
                    await bus.publish(
                        ActionCompleted(
                            request_id=ev.request_id,
                            action=ev.action,
                            ok=result.ok,
                            detail=result.summary[:160],
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception("vision_action_crashed", error=str(exc))
                    await bus.publish(
                        ActionCompleted(
                            request_id=ev.request_id,
                            action=ev.action,
                            ok=False,
                            detail=f"screen_inspect crashed: {exc}",
                        )
                    )

    work: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=16)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_from_vision_events(work), name="vision-req-fanin")
            tg.create_task(_from_action_events(work), name="vision-action-fanin")
            tg.create_task(_worker(work), name="vision-worker")
    except asyncio.CancelledError:
        log.info("vision_service_cancelled")
        raise
    finally:
        bus.unsubscribe(VisionRequested, vision_q)
        bus.unsubscribe(ActionRequested, action_q)
