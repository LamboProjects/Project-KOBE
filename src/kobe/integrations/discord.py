"""Discord webhook alert service.

Subscribes to `PrinterAlert` (with 3 s dedupe) and `PrinterStatus` (cached for
embed enrichment). Optionally spawns a periodic digest task that posts the
latest `PrinterStatus` every N hours. One `httpx.AsyncClient` is reused.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import PrinterAlert, PrinterStatus

log = structlog.get_logger(__name__)

_DEDUPE_WINDOW_S = 3.0
_HTTP_TIMEOUT_S = 10.0
_CONTENT_CAP = 1800
_DESCRIPTION_CAP = 1800
_PROGRESS_BAR_WIDTH = 20
_DIGEST_COLOR = 0x3B88C3  # neutral blue
_RETRY_AFTER_CEILING_S = 300.0  # never block longer than 5 minutes on a 429

# kind -> (emoji, color)
_KIND_STYLE: dict[str, tuple[str, int]] = {
    "started": ("\U0001F5A8\uFE0F", 0x00D4FF),   # printer
    "completed": ("\u2705", 0x2ECC71),            # check
    "failed": ("\u274C", 0xE74C3C),               # cross
    "paused": ("\u23F8\uFE0F", 0xF39C12),         # pause
    "resumed": ("\u25B6\uFE0F", 0x3498DB),        # play
}
_UNKNOWN_STYLE: tuple[str, int] = ("\U0001F4E3", 0x95A5A6)  # megaphone

# Module-internal cache of the latest PrinterStatus, populated by the
# PrinterStatus listener task. Single-writer, read by alert + digest paths.
last_status: dict[str, PrinterStatus | None] = {"value": None}


def _style_for(kind: str) -> tuple[str, int]:
    return _KIND_STYLE.get(kind, _UNKNOWN_STYLE)


def _progress_bar(pct: float, width: int = _PROGRESS_BAR_WIDTH) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round((pct / 100.0) * width))
    return ("\u25B0" * filled) + ("\u25B1" * (width - filled)) + f"  {int(round(pct))}%"


def _truncate(s: str, cap: int) -> str:
    return s if len(s) <= cap else s[: cap - 1] + "\u2026"


def _status_fields(status: PrinterStatus) -> list[dict]:
    return [
        {"name": "Progress", "value": f"{int(round(status.progress_pct))}%", "inline": True},
        {"name": "Remaining", "value": f"{status.remaining_minutes} min", "inline": True},
        {"name": "Nozzle", "value": f"{int(round(status.nozzle_temp_c))}\u00B0C", "inline": True},
        {"name": "Bed", "value": f"{int(round(status.bed_temp_c))}\u00B0C", "inline": True},
        {"name": "Stage", "value": status.stage, "inline": True},
    ]


def _build_alert_payload(alert: PrinterAlert, settings: Settings) -> dict:
    emoji, color = _style_for(alert.kind)
    description = alert.message
    fields: list[dict] = [
        {"name": "File", "value": alert.filename or "(n/a)", "inline": True},
    ]
    status = last_status["value"]
    if settings.discord_include_snapshot and status is not None:
        description = f"{_progress_bar(status.progress_pct)}\n{description}"
        fields.extend(_status_fields(status))

    embed = {
        "title": alert.kind.upper(),
        "description": _truncate(description, _DESCRIPTION_CAP),
        "color": color,
        "fields": fields,
    }
    return {
        "username": "KOBE",
        "content": _truncate(f"{emoji} {alert.message}", _CONTENT_CAP),
        "embeds": [embed],
    }


def _build_digest_payload(status: PrinterStatus) -> dict:
    description = (
        f"{_progress_bar(status.progress_pct)}\n"
        f"File: {status.filename or '(n/a)'}"
    )
    embed = {
        "title": "KOBE digest",
        "description": _truncate(description, _DESCRIPTION_CAP),
        "color": _DIGEST_COLOR,
        "fields": _status_fields(status),
    }
    return {
        "username": "KOBE",
        "content": _truncate(
            f"\U0001F4CA Printer digest \u2014 {status.stage} ({int(round(status.progress_pct))}%)",
            _CONTENT_CAP,
        ),
        "embeds": [embed],
    }


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """Parse Retry-After from a 429 response.

    The HTTP `Retry-After` header is always seconds (per RFC 7231 and Discord's
    current behaviour). The JSON body's `retry_after` field historically used
    milliseconds in some legacy docs, so we apply a `>120 -> ms` heuristic
    there only. Both paths are clamped to `_RETRY_AFTER_CEILING_S` so a bad
    value never blocks the service for minutes.
    """
    raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if raw is not None:
        try:
            seconds = float(raw)
        except ValueError:
            return None
        if seconds < 0:
            return None
        return min(seconds, _RETRY_AFTER_CEILING_S)

    # Fall back to the JSON body; here the ms heuristic is still warranted.
    try:
        body = resp.json()
    except Exception:
        return None
    val = body.get("retry_after") if isinstance(body, dict) else None
    if val is None:
        return None
    try:
        raw_val = float(val)
    except (TypeError, ValueError):
        return None
    if raw_val < 0:
        return None
    seconds = raw_val / 1000.0 if raw_val > 120 else raw_val
    return min(seconds, _RETRY_AFTER_CEILING_S)


async def _post(client: httpx.AsyncClient, url: str, payload: dict, *, tag: str) -> None:
    """Post once, retry once on 429 honoring Retry-After, then give up."""
    for attempt in (1, 2):
        try:
            resp = await client.post(url, json=payload)
        except httpx.HTTPError as e:
            log.warning("discord_request_failed", error=str(e), tag=tag, attempt=attempt)
            return
        if resp.status_code == 429 and attempt == 1:
            wait_s = _retry_after_seconds(resp) or 1.0
            log.warning("discord_ratelimited", tag=tag, wait_s=round(wait_s, 2))
            await asyncio.sleep(wait_s)
            continue
        if resp.status_code >= 400:
            log.warning(
                "discord_http_error",
                status=resp.status_code,
                tag=tag,
                attempt=attempt,
                body=resp.text[:200],
            )
            return
        log.debug("discord_sent", tag=tag, status=resp.status_code, attempt=attempt)
        return


async def _status_cache_task(bus: Bus) -> None:
    """Keep `last_status` current. Never raises to the bus.

    Per-event processing is wrapped in an inner try/except so a single
    malformed payload can't kill the cache for the whole session;
    `asyncio.CancelledError` is re-raised to honour cooperative shutdown.
    """
    try:
        async with bus.stream(PrinterStatus) as queue:
            while True:
                try:
                    status = await queue.get()
                    last_status["value"] = status
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("discord_status_cache_event_error", error=str(e))
                    continue
    except asyncio.CancelledError:
        raise
    except Exception as e:  # defensive — subscriber must never take down the service
        log.warning("discord_status_cache_error", error=str(e))


async def _digest_task(client: httpx.AsyncClient, url: str, interval_hours: float) -> None:
    """Every `interval_hours`, post a neutral digest of the latest PrinterStatus.

    Floors at 60 s to avoid rate-limit spam. If the user set a fractional
    sub-minute value (e.g. `0.01` → 36 s), we log at startup that we're
    rounding up so the behaviour isn't surprising.
    """
    raw_s = float(interval_hours) * 3600.0
    interval_s = max(60.0, raw_s)
    if interval_s > raw_s:
        log.info(
            "discord_digest_interval_floored",
            requested_s=round(raw_s, 1),
            effective_s=interval_s,
            hint="digest interval floors at 60 s",
        )
    try:
        while True:
            await asyncio.sleep(interval_s)
            status = last_status["value"]
            if status is None:
                log.debug("discord_digest_skipped_no_status")
                continue
            try:
                await _post(client, url, _build_digest_payload(status), tag="digest")
            except Exception as e:
                log.warning("discord_digest_failed", error=str(e))
    except asyncio.CancelledError:
        raise


async def run_discord_service(bus: Bus, settings: Settings) -> None:
    if not settings.discord_webhook_url:
        log.info("discord_unconfigured")
        return

    webhook_url = settings.discord_webhook_url
    client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S)
    # (kind, message, filename) -> monotonic timestamp of last send
    last_seen: dict[tuple[str, str, str], float] = {}
    # `last_status` is module-global so the digest task can read it without
    # threading state around. Reset it on every service start so a supervised
    # restart (or a test that re-runs the service in-process) can't enrich
    # the first alert with the previous run's printer snapshot.
    last_status["value"] = None

    # PrinterStatus is now drained inline in the alert loop (see below) to
    # avoid cross-task ordering drift. The standalone `_status_cache_task`
    # is kept around only for the digest path, which doesn't need ordering.
    status_task = asyncio.create_task(_status_cache_task(bus), name="discord_status_cache")
    digest_task: asyncio.Task | None = None
    if settings.discord_digest_interval_hours > 0:
        digest_task = asyncio.create_task(
            _digest_task(client, webhook_url, settings.discord_digest_interval_hours),
            name="discord_digest",
        )

    log.info(
        "discord_service_started",
        include_snapshot=settings.discord_include_snapshot,
        digest_hours=settings.discord_digest_interval_hours,
    )
    try:
        # Subscribe to BOTH PrinterStatus and PrinterAlert in this same task so
        # we can drain pending status updates *before* enriching an alert. Two
        # independent subscriber tasks (status cache + alert handler) don't
        # share ordering across event types, so an alert that fires immediately
        # after a fresh status could otherwise carry the previous job's
        # progress/file/temps. Inline draining closes that race.
        status_q = bus.subscribe(PrinterStatus)
        alert_q = bus.subscribe(PrinterAlert)
        try:
            while True:
                alert = await alert_q.get()
                # Drain every status currently in our queue so `last_status`
                # reflects everything Bambu published up to this alert.
                while True:
                    try:
                        status = status_q.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    last_status["value"] = status

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
                if len(last_seen) > 128:
                    cutoff = now - _DEDUPE_WINDOW_S
                    last_seen = {k: v for k, v in last_seen.items() if v >= cutoff}

                try:
                    payload = _build_alert_payload(alert, settings)
                    await _post(client, webhook_url, payload, tag=f"alert:{alert.kind}")
                except Exception as e:
                    log.warning("discord_alert_failed", error=str(e), kind=alert.kind)
        finally:
            bus.unsubscribe(PrinterStatus, status_q)
            bus.unsubscribe(PrinterAlert, alert_q)
    except asyncio.CancelledError:
        log.info("discord_service_cancelled")
        raise
    finally:
        for t in (status_task, digest_task):
            if t is not None and not t.done():
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        await client.aclose()
