"""Phase 3 smoke test.

Exercises the two most integration-heavy Phase 3 fixes without touching
external APIs (no Bambu printer, no Spotify OAuth, no Discord webhook):

1. Action executor only responds to actions in its allowlist — it must NOT
   emit a bogus `ActionCompleted(ok=False)` for a `bambu_cancel_print` or
   other integration-owned action.
2. Confirmation flow: publishing a `ConfirmationRequested` causes a prompt
   `ResponseReady`, and a subsequent "yes" `TranscriptReady` produces a
   `ConfirmationResult(confirmed=True)` + a republished `ActionRequested`.
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
    ConfirmationRequested,
    ConfirmationResult,
    ResponseReady,
    TranscriptReady,
)
from kobe.logging import configure_logging


async def _drain_until(bus: Bus, event_type: type, timeout: float, predicate=None):
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
    log = structlog.get_logger("smoke3")

    settings = load_settings()
    bus = Bus()

    from kobe.actions.executor import run_action_executor
    from kobe.actions.confirmation import run_confirmation_service

    executor_task = asyncio.create_task(run_action_executor(bus, settings))
    confirm_task = asyncio.create_task(run_confirmation_service(bus, settings))
    await asyncio.sleep(0.1)  # let them subscribe

    # --- Test 1: executor must NOT respond to a non-owned action.
    # We collect ActionCompleted events and assert none arrive for bambu_cancel_print.
    seen_completed: list[ActionCompleted] = []
    q = bus.subscribe(ActionCompleted)

    async def _collect():
        while True:
            seen_completed.append(await q.get())

    collector = asyncio.create_task(_collect())
    try:
        await bus.publish(
            ActionRequested(request_id="t1", action="bambu_cancel_print", params={})
        )
        await asyncio.sleep(0.5)  # give the executor time to NOT respond
        assert not seen_completed, f"executor emitted for non-owned action: {seen_completed}"
        log.info("test_1_pass_no_bogus_completion")

        # Sanity: executor SHOULD respond to noop.
        await bus.publish(
            ActionRequested(request_id="t1b", action="noop", params={})
        )
        noop_done = await asyncio.wait_for(q.get(), timeout=2.0)
        assert noop_done.action == "noop" and noop_done.ok, noop_done
        log.info("test_1b_pass_noop_still_works")
    finally:
        collector.cancel()
        bus.unsubscribe(ActionCompleted, q)

    # --- Test 2: confirmation flow.
    # Subscribe to the events the confirmation service will emit.
    #   prompt     = ResponseReady with text matching the request
    #   result     = ConfirmationResult(confirmed=True)
    #   follow-on  = ActionRequested republished with the original action name
    prompt_task = asyncio.create_task(
        _drain_until(bus, ResponseReady, timeout=3.0, predicate=lambda e: e.request_id == "t2")
    )
    await bus.publish(
        ConfirmationRequested(
            request_id="t2",
            action="bambu_cancel_print",
            params={"reason": "user requested"},
            prompt="Cancel the print. Confirm?",
        )
    )
    prompt = await prompt_task
    assert prompt is not None, "no confirmation prompt was spoken"
    assert "cancel the print" in prompt.text.lower(), prompt.text
    log.info("test_2a_pass_prompt_spoken", text=prompt.text)

    # User says yes.
    result_task = asyncio.create_task(
        _drain_until(bus, ConfirmationResult, timeout=3.0, predicate=lambda e: e.request_id == "t2")
    )
    action_task = asyncio.create_task(
        _drain_until(
            bus,
            ActionRequested,
            timeout=3.0,
            predicate=lambda e: e.request_id == "t2" and e.action == "bambu_cancel_print",
        )
    )
    await bus.publish(
        TranscriptReady(request_id="user", text="yes", duration_s=0.4)
    )
    result = await result_task
    action = await action_task
    assert result is not None and result.confirmed, result
    assert action is not None and action.params == {"reason": "user requested"}, action
    log.info("test_2b_pass_yes_confirmed_and_action_republished")

    executor_task.cancel()
    confirm_task.cancel()
    for t in (executor_task, confirm_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    log.info("smoke_phase3_ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
