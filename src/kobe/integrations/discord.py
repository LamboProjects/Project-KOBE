"""Discord webhook alert service.

Subscribes to `PrinterAlert` events and posts formatted messages to a Discord
channel via incoming webhook. One `httpx.AsyncClient` is reused for the
lifetime of the service. Identical alerts fired within 3 seconds are coalesced.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import PrinterAlert

log = structlog.get_logger(__name__)

_DEDUPE_WINDOW_S = 3.0
_HTTP_TIMEOUT_S = 10.0

# kind -> (emoji, color)
_KIND_STYLE: dict[str, tuple[str, int]] = {
    "started": ("\U0001F5A8\uFE0F", 0x00D4FF),   # printer
    "completed": ("\u2705", 0x2ECC71),            # check
    "failed": ("\u274C", 0xE74C3C),               # cross
    "paused": ("\u23F8\uFE0F", 0xF39C12),         # pause
    "resumed": ("\u25B6\uFE0F", 0x3498DB),        # play
}
_UNKNOWN_STYLE: tuple[str, int] = ("\U0001F4E3", 0x95A5A6)  # megaphone


def _style_for(kind: str) -> tuple[str, int]:
    return _KIND_STYLE.get(kind, _UNKNOWN_STYLE)


def _build_payload(alert: PrinterAlert) -> dict:
    emoji, color = _style_for(alert.kind)
    embed: dict = {
        "title": alert.kind.upper(),
        "description": alert.message,
        "color": color,
        "fields": [
            {"name": "File", "value": alert.filename or "(n/a)", "inline": True},
        ],
    }
    return {
        "username": "KOBE",
        "content": f"{emoji} {alert.message}",
        "embeds": [embed],
    }


async def run_discord_service(bus: Bus, settings: Settings) -> None:
    if not settings.discord_webhook_url:
        log.info("discord_unconfigured")
        return

    webhook_url = settings.discord_webhook_url
    client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S)
    # (kind, message, filename) -> monotonic timestamp of last send
    last_seen: dict[tuple[str, str, str], float] = {}

    log.info("discord_service_started")
    try:
        async with bus.stream(PrinterAlert) as queue:
            while True:
                alert = await queue.get()
                key = (alert.kind, alert.message, alert.filename)
                now = time.monotonic()
                prev = last_seen.get(key)
                if prev is not None and (now - prev) < _DEDUPE_WINDOW_S:
                    log.debug(
                        "discord_alert_deduped",
                        kind=alert.kind,
                        filename=alert.filename,
                        age_s=round(now - prev, 2),
                    )
                    continue
                last_seen[key] = now
                # Occasional cleanup so the dict doesn't grow unbounded.
                if len(last_seen) > 128:
                    cutoff = now - _DEDUPE_WINDOW_S
                    last_seen = {k: v for k, v in last_seen.items() if v >= cutoff}

                payload = _build_payload(alert)
                try:
                    resp = await client.post(webhook_url, json=payload)
                    resp.raise_for_status()
                    log.debug(
                        "discord_alert_sent",
                        kind=alert.kind,
                        status=resp.status_code,
                    )
                except httpx.HTTPStatusError as e:
                    log.warning(
                        "discord_http_error",
                        status=e.response.status_code,
                        kind=alert.kind,
                        body=e.response.text[:200],
                    )
                except httpx.HTTPError as e:
                    log.warning(
                        "discord_request_failed",
                        error=str(e),
                        kind=alert.kind,
                    )
    except asyncio.CancelledError:
        log.info("discord_service_cancelled")
        raise
    finally:
        await client.aclose()
