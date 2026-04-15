"""Phase 4 foundation smoke test.

Exercises the screen-vision pipeline with the null backend:

1. Publishing `VisionRequested` triggers capture → backend → `VisionResult`
   + a `ResponseReady` with the backend's summary.
2. Publishing `ActionRequested("screen_inspect", params)` also triggers the
   same path and produces an `ActionCompleted`.
3. Actions outside the vision namespace are ignored by the vision service
   (no phantom `VisionResult` / `ActionCompleted`).

Runs on any Windows machine with a screen — no API keys, no GPU.
Requires mss + pillow (already deps).
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from kobe.bus import Bus
from kobe.config import load_settings
from kobe.events import (
    ActionCompleted,
    ActionRequested,
    ResponseReady,
    VisionRequested,
    VisionResult,
)
from kobe.logging import configure_logging


async def _first(bus: Bus, event_type: type, *, timeout: float, predicate=None):
    q = bus.subscribe(event_type)
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return None
            try:
                ev = await asyncio.wait_for(q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if predicate is None or predicate(ev):
                return ev
    finally:
        bus.unsubscribe(event_type, q)


async def main() -> int:
    configure_logging("INFO")
    log = structlog.get_logger("smoke4")

    settings = load_settings()
    # Force the settings this smoke test relies on so it doesn't inherit a
    # `.env` that disables vision or swaps in an unimplemented backend.
    settings.vision_enabled = True
    settings.vision_backend = "null"
    settings.vision_save_screenshots = False  # keep the disk clean
    settings.vision_max_capture_seconds = max(settings.vision_max_capture_seconds, 5.0)

    bus = Bus()
    from kobe.vision.service import run_vision_service

    svc = asyncio.create_task(run_vision_service(bus, settings))
    await asyncio.sleep(0.2)  # let it subscribe

    # --- Test 1: direct VisionRequested → VisionResult + ResponseReady.
    result_task = asyncio.create_task(
        _first(bus, VisionResult, timeout=8.0, predicate=lambda e: e.request_id == "v1")
    )
    response_task = asyncio.create_task(
        _first(bus, ResponseReady, timeout=8.0, predicate=lambda e: e.request_id == "v1")
    )
    await bus.publish(
        VisionRequested(
            request_id="v1",
            question="what's on my screen?",
            mode="foreground",
        )
    )
    result = await result_task
    response = await response_task
    assert result is not None and result.ok, f"bad VisionResult: {result}"
    assert result.width > 0 and result.height > 0, f"empty capture: {result}"
    assert result.backend == "null", result.backend
    assert result.mode in ("foreground", "full"), result.mode
    assert result.context_name, f"missing context_name: {result}"
    assert response is not None and response.text.strip(), response
    log.info(
        "test_1_pass",
        width=result.width,
        height=result.height,
        summary_chars=len(result.summary),
        mode=result.mode,
        context_name=result.context_name,
    )

    # --- Test 2: ActionRequested("screen_inspect", ...) → VisionResult + ActionCompleted.
    result_task = asyncio.create_task(
        _first(bus, VisionResult, timeout=8.0, predicate=lambda e: e.request_id == "v2")
    )
    action_done_task = asyncio.create_task(
        _first(
            bus,
            ActionCompleted,
            timeout=8.0,
            predicate=lambda e: e.request_id == "v2" and e.action == "screen_inspect",
        )
    )
    await bus.publish(
        ActionRequested(
            request_id="v2",
            action="screen_inspect",
            params={"question": "describe this window", "mode": "foreground"},
        )
    )
    r2 = await result_task
    done2 = await action_done_task
    assert r2 is not None and r2.ok, f"action → VisionResult failed: {r2}"
    assert done2 is not None and done2.ok, f"ActionCompleted missing/failed: {done2}"
    log.info("test_2_pass", action=done2.action, ok=done2.ok)

    # --- Test 3: unrelated action is ignored — no VisionResult for it.
    bogus_result_task = asyncio.create_task(
        _first(bus, VisionResult, timeout=1.5, predicate=lambda e: e.request_id == "v3")
    )
    bogus_ac_task = asyncio.create_task(
        _first(
            bus,
            ActionCompleted,
            timeout=1.5,
            predicate=lambda e: e.request_id == "v3" and e.action == "bambu_cancel_print",
        )
    )
    await bus.publish(
        ActionRequested(request_id="v3", action="bambu_cancel_print", params={})
    )
    r3 = await bogus_result_task
    ac3 = await bogus_ac_task
    assert r3 is None, f"vision service responded to a non-owned action: {r3}"
    assert ac3 is None, f"vision service emitted ActionCompleted for non-owned action: {ac3}"
    log.info("test_3_pass_no_cross_namespace_firing")

    svc.cancel()
    try:
        await svc
    except (asyncio.CancelledError, Exception):
        pass

    log.info("smoke_phase4_ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
