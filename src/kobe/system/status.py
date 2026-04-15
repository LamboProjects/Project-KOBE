"""Periodic system-status telemetry service.

Publishes `SystemStatus` events on the bus at a fixed interval so the HUD can
display the active foreground app, CPU usage, and memory usage.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import psutil
import pygetwindow
import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import SystemStatus

log = structlog.get_logger(__name__)

_MAX_TITLE_LEN = 80


def _foreground_title() -> str:
    """Return the active window title, or 'unknown' if unavailable.

    `pygetwindow.getActiveWindow()` can raise on Windows when the desktop
    itself has focus, so swallow any exception and fall back to 'unknown'.
    """
    try:
        win = pygetwindow.getActiveWindow()
    except Exception as exc:  # noqa: BLE001 - pygetwindow raises bare Exception on Win
        log.debug("foreground_window_error", error=str(exc))
        return "unknown"
    if win is None:
        return "unknown"
    title = getattr(win, "title", None) or ""
    if not title:
        return "unknown"
    return title[:_MAX_TITLE_LEN]


def _sample() -> tuple[str, float, float]:
    """Collect a single telemetry sample. Runs in a worker thread."""
    title = _foreground_title()
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    return title, cpu, mem


async def run_system_status_service(bus: Bus, settings: Settings) -> None:
    """Publish `SystemStatus` events every `settings.system_status_interval_s`."""
    interval = settings.system_status_interval_s
    log.info("system_status_service_started", interval_s=interval)
    # Prime cpu_percent so the first real sample isn't the documented 0.0
    # that `psutil.cpu_percent(interval=None)` returns before any baseline.
    try:
        await asyncio.to_thread(psutil.cpu_percent, None)
    except Exception as exc:  # noqa: BLE001
        log.debug("cpu_percent_prime_failed", error=str(exc))
    try:
        while True:
            try:
                title, cpu, mem = await asyncio.to_thread(_sample)
                event = SystemStatus(
                    foreground_app=title,
                    cpu_percent=cpu,
                    memory_percent=mem,
                    timestamp_iso=datetime.now(timezone.utc).isoformat(),
                )
                await bus.publish(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - never kill the loop over telemetry
                log.warning("system_status_sample_failed", error=str(exc))
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("system_status_service_cancelled")
        raise
