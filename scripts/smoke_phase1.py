"""Phase 1 smoke test.

Import every module, run the bus in isolation, drive a synthetic event through
Brain (stub mode) → TTS (no-op when no keys) → Actions (noop). Confirms that
the wiring is intact without needing a microphone, speakers, or any API keys.

Run:
    uv run python scripts/smoke_phase1.py
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
    SpeakFinished,
    TranscriptReady,
)
from kobe.logging import configure_logging


async def _collect_once(bus: Bus, event_type: type, timeout: float = 5.0):
    q = bus.subscribe(event_type)
    try:
        return await asyncio.wait_for(q.get(), timeout=timeout)
    finally:
        bus.unsubscribe(event_type, q)


async def main() -> int:
    configure_logging("INFO")
    log = structlog.get_logger("smoke")

    settings = load_settings()
    # Force stub mode for the brain even if a user has config/.env set up.
    settings.openclaw_api_key = ""
    settings.openclaw_api_url = ""

    bus = Bus()

    # Import services to confirm imports work.
    from kobe.brain.router import run_brain_service
    from kobe.actions.executor import run_action_executor

    log.info("smoke_start")

    async with asyncio.TaskGroup() as tg:
        brain_task = tg.create_task(run_brain_service(bus, settings))
        actions_task = tg.create_task(run_action_executor(bus, settings))

        # Give services a tick to subscribe.
        await asyncio.sleep(0.1)

        # Drive a synthetic transcript through the brain.
        await bus.publish(TranscriptReady(request_id="smoke-1", text="hello kobe", duration_s=1.0))
        resp = await _collect_once(bus, ResponseReady, timeout=5.0)
        log.info("smoke_got_response", text=resp.text, request_id=resp.request_id)
        assert resp.text.startswith("You said:"), f"Expected stub echo, got {resp.text!r}"

        # Drive a noop action through the executor.
        await bus.publish(ActionRequested(request_id="smoke-2", action="noop", params={}))
        done = await _collect_once(bus, ActionCompleted, timeout=5.0)
        log.info("smoke_got_action_completed", ok=done.ok, detail=done.detail)
        assert done.ok, f"Expected noop to succeed, got {done.detail!r}"

        brain_task.cancel()
        actions_task.cancel()

    log.info("smoke_ok")
    return 0


if __name__ == "__main__":
    # The TaskGroup raises an ExceptionGroup on cancellation; swallow it at the
    # top level since both tasks were cancelled intentionally.
    try:
        sys.exit(asyncio.run(main()))
    except* asyncio.CancelledError:
        sys.exit(0)
