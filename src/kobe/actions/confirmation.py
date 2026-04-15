"""Confirmation manager.

Listens for `ConfirmationRequested` events, speaks the prompt via `ResponseReady`,
waits for the next `TranscriptReady`, classifies yes/no, and either dispatches the
underlying `ActionRequested` or announces cancellation. Processes confirmations
strictly sequentially so two prompts never compete for the microphone.
"""
from __future__ import annotations

import asyncio
import re

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    ActionRequested,
    ConfirmationRequested,
    ConfirmationResult,
    ResponseReady,
    TranscriptReady,
)

log = structlog.get_logger(__name__)


def _drain(q: asyncio.Queue) -> int:
    """Remove any events already sitting in the queue. Returns drop count."""
    dropped = 0
    while True:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            return dropped
        dropped += 1


def _classify(text: str, yes_list: list[str], no_list: list[str]) -> bool | None:
    """Return True=confirmed, False=denied, None=ambiguous.

    `no` wins ties: if any no-phrase matches, the answer is denied even if a
    yes-phrase also appears (safer default for destructive actions).
    """
    norm = text.strip().lower()
    if not norm:
        return None
    # Token set for whole-word single-token matches.
    tokens = set(re.findall(r"[a-z']+", norm))

    def _hit(phrases: list[str]) -> bool:
        for phrase in phrases:
            p = phrase.strip().lower()
            if not p:
                continue
            if " " in p:
                if p in norm:
                    return True
            else:
                if p in tokens:
                    return True
        return False

    no_hit = _hit(no_list)
    yes_hit = _hit(yes_list)
    if no_hit:
        return False
    if yes_hit:
        return True
    return None


async def _handle_one(
    bus: Bus,
    settings: Settings,
    event: ConfirmationRequested,
) -> None:
    """Run the full confirm/deny cycle for a single request."""
    transcript_q = bus.subscribe(TranscriptReady)
    try:
        _drain(transcript_q)
        await bus.publish(ResponseReady(request_id=event.request_id, text=event.prompt))

        try:
            transcript: TranscriptReady = await asyncio.wait_for(
                transcript_q.get(), timeout=settings.confirmation_timeout_s
            )
        except asyncio.TimeoutError:
            log.info("confirmation_timeout", request_id=event.request_id, action=event.action)
            await bus.publish(
                ConfirmationResult(
                    request_id=event.request_id, action=event.action, confirmed=False
                )
            )
            await bus.publish(
                ResponseReady(request_id=event.request_id, text="Cancelled.")
            )
            return

        verdict = _classify(
            transcript.text, settings.confirmation_yes_list, settings.confirmation_no_list
        )
        confirmed = verdict is True
        if verdict is None:
            log.info(
                "confirmation_ambiguous",
                request_id=event.request_id,
                action=event.action,
                text=transcript.text,
            )
        else:
            log.info(
                "confirmation_classified",
                request_id=event.request_id,
                action=event.action,
                confirmed=confirmed,
                text=transcript.text,
            )

        await bus.publish(
            ConfirmationResult(
                request_id=event.request_id, action=event.action, confirmed=confirmed
            )
        )
        if confirmed:
            await bus.publish(
                ActionRequested(
                    request_id=event.request_id, action=event.action, params=event.params
                )
            )
        else:
            await bus.publish(
                ResponseReady(request_id=event.request_id, text="Cancelled.")
            )
    finally:
        bus.unsubscribe(TranscriptReady, transcript_q)


async def run_confirmation_service(bus: Bus, settings: Settings) -> None:
    """Service entry point. Consumes `ConfirmationRequested` events sequentially."""
    request_q = bus.subscribe(ConfirmationRequested)
    log.info("confirmation_service_started", timeout_s=settings.confirmation_timeout_s)
    try:
        while True:
            event: ConfirmationRequested = await request_q.get()
            try:
                await _handle_one(bus, settings, event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "confirmation_handler_error",
                    request_id=event.request_id,
                    action=event.action,
                    error=str(exc),
                )
    except asyncio.CancelledError:
        log.info("confirmation_service_cancelled")
        raise
    finally:
        bus.unsubscribe(ConfirmationRequested, request_q)
