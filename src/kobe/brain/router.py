"""Conversation router — KOBE brain service.

Bridges the local voice pipeline to the remote OpenClaw HTTP brain. Consumes
`TranscriptReady` events from the bus, forwards the text to OpenClaw, and
publishes `ResponseReady` (and optionally `ActionRequested`) so downstream TTS
and action executors can do their work.

HTTP contract (OpenClaw side must implement this endpoint):
    POST {openclaw_api_url}/v1/chat
    Headers:
        Authorization: Bearer {openclaw_api_key}
        Content-Type:  application/json
    Body (JSON):
        {
            "agent":      str,   # settings.openclaw_agent
            "request_id": str,   # correlation id from TranscriptReady
            "text":       str    # user utterance
        }
    Response (JSON, 200 OK):
        {
            "text":   str,
            "action": {
                "name":                  str,
                "params":                dict,
                # Optional. When true OR when the name is in the built-in
                # destructive allowlist, we publish a `ConfirmationRequested`
                # instead of an `ActionRequested` — the confirmation service
                # will speak the prompt and listen for yes/no before the real
                # dispatch.
                "requires_confirmation": bool,   # optional
                "prompt":                str     # optional, TTS reads this
            } | null
        }

Failure modes (timeout, HTTP >= 400, network error, bad JSON) are logged and
collapsed into a single spoken fallback so the TTS layer never stalls. This
module never raises into the bus.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    ActionRequested,
    ConfirmationRequested,
    ResponseReady,
    TranscriptReady,
)

log = structlog.get_logger(__name__)

FALLBACK_TEXT = "I can't reach my brain right now."

# Built-in destructive-action allowlist — actions named here always route through
# the confirmation manager, even if the brain response doesn't set
# `requires_confirmation: true`. Integrations can grow this list over time.
_DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "bambu_cancel_print",
    "bambu_pause_print",
})

# Default prompt used when the brain didn't supply one.
_DEFAULT_PROMPTS: dict[str, str] = {
    "bambu_cancel_print": "Cancel the print. Confirm?",
    "bambu_pause_print": "Pause the print. Confirm?",
}


def _is_stub_mode(settings: Settings) -> bool:
    """Stub mode when the brain isn't configured — keeps dev loop usable."""
    url = (settings.openclaw_api_url or "").strip()
    key = (settings.openclaw_api_key or "").strip()
    return not url or not key


async def _publish_fallback(bus: Bus, request_id: str) -> None:
    await bus.publish(ResponseReady(request_id=request_id, text=FALLBACK_TEXT))


async def _call_openclaw(
    client: httpx.AsyncClient,
    settings: Settings,
    request_id: str,
    text: str,
) -> dict[str, Any] | None:
    """POST to OpenClaw. Returns decoded JSON on success, None on any failure."""
    url = settings.openclaw_api_url.rstrip("/") + "/v1/chat"
    headers = {
        "Authorization": f"Bearer {settings.openclaw_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "agent": settings.openclaw_agent,
        "request_id": request_id,
        "text": text,
    }
    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            log.error("openclaw_bad_response", request_id=request_id, body=str(data)[:200])
            return None
        return data
    except httpx.TimeoutException as e:
        log.error("openclaw_timeout", request_id=request_id, error=str(e))
    except httpx.HTTPStatusError as e:
        log.error(
            "openclaw_http_error",
            request_id=request_id,
            status=e.response.status_code,
            body=e.response.text[:200],
        )
    except httpx.HTTPError as e:
        log.error("openclaw_network_error", request_id=request_id, error=str(e))
    except ValueError as e:  # JSON decode
        log.error("openclaw_json_error", request_id=request_id, error=str(e))
    return None


async def _handle_transcript(
    event: TranscriptReady,
    bus: Bus,
    settings: Settings,
    client: httpx.AsyncClient | None,
) -> None:
    text = (event.text or "").strip()
    if not text:
        log.info("empty_transcript_skipped", request_id=event.request_id)
        return

    if client is None:
        log.info("stub_mode", request_id=event.request_id, text=text)
        await bus.publish(ResponseReady(request_id=event.request_id, text=f"You said: {text}"))
        return

    log.info("brain_request", request_id=event.request_id, text=text)
    data = await _call_openclaw(client, settings, event.request_id, text)
    if data is None:
        await _publish_fallback(bus, event.request_id)
        return

    reply_text: str = data["text"]
    await bus.publish(ResponseReady(request_id=event.request_id, text=reply_text))

    action = data.get("action")
    if isinstance(action, dict):
        name = action.get("name")
        params = action.get("params", {})
        if isinstance(name, str) and name and isinstance(params, dict):
            requires_confirmation = (
                bool(action.get("requires_confirmation"))
                or name in _DESTRUCTIVE_ACTIONS
            )
            if requires_confirmation:
                prompt = action.get("prompt")
                if not isinstance(prompt, str) or not prompt.strip():
                    prompt = _DEFAULT_PROMPTS.get(name, f"Confirm {name}?")
                log.info(
                    "confirmation_requested",
                    request_id=event.request_id,
                    action=name,
                    prompt=prompt,
                )
                await bus.publish(
                    ConfirmationRequested(
                        request_id=event.request_id,
                        action=name,
                        params=params,
                        prompt=prompt,
                    )
                )
            else:
                log.info("action_dispatch", request_id=event.request_id, action=name)
                await bus.publish(
                    ActionRequested(request_id=event.request_id, action=name, params=params)
                )
        else:
            log.warning("openclaw_bad_action", request_id=event.request_id, action=str(action)[:200])


async def run_brain_service(bus: Bus, settings: Settings) -> None:
    """Long-running coroutine: route TranscriptReady events through OpenClaw."""
    stub = _is_stub_mode(settings)
    client: httpx.AsyncClient | None = None
    if stub:
        log.info("stub_mode_active", reason="openclaw_api_url or openclaw_api_key not set")
    else:
        client = httpx.AsyncClient(timeout=settings.openclaw_timeout_s)
        log.info(
            "brain_service_started",
            url=settings.openclaw_api_url,
            agent=settings.openclaw_agent,
            timeout_s=settings.openclaw_timeout_s,
        )

    queue = bus.subscribe(TranscriptReady)
    try:
        while True:
            event = await queue.get()
            try:
                await _handle_transcript(event, bus, settings, client)
            except Exception as e:  # never raise into the bus
                log.exception("brain_handler_crashed", request_id=event.request_id, error=str(e))
                await _publish_fallback(bus, event.request_id)
    except asyncio.CancelledError:
        log.info("brain_service_cancelled")
        raise
    finally:
        bus.unsubscribe(TranscriptReady, queue)
        if client is not None:
            await client.aclose()
            log.info("brain_service_stopped")
