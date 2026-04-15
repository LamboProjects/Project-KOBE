"""Steam integration for Project KOBE.

Listens for `ActionRequested` events on the bus and launches Steam games via the
`steam://rungameid/{app_id}` URI scheme. Supports a small built-in alias map so
users can say "launch CS2" without needing to know the numeric app id.

Handled actions:
  - `steam_launch_game` with params `{"app_id": int}` or `{"name": str}`
  - `steam_open` (no params) — opens the Steam client main window

Anything else is ignored.
"""
from __future__ import annotations

import asyncio
import os

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested

log = structlog.get_logger(__name__)

# Small local alias map. Keys are normalized lowercase names; values are Steam app ids.
# NOTE: Valorant is NOT on Steam — included as an explicit sentinel so we can give a
# useful error message rather than silently failing a lookup.
STEAM_ALIASES: dict[str, int | None] = {
    "cs2": 730,
    "counter-strike 2": 730,
    "dota2": 570,
    "dota 2": 570,
    "gtav": 271590,
    "gta v": 271590,
    "grand theft auto v": 271590,
    "rust": 252490,
    "valorant": None,  # not on Steam — see note above
    "elden ring": 1245620,
    "baldurs gate 3": 1086940,
    "baldur's gate 3": 1086940,
    "cyberpunk 2077": 1091500,
    "rocket league": 252950,
    "apex legends": 1172470,
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _lookup_app_id(name: str) -> int | None:
    return STEAM_ALIASES.get(_normalize(name))


async def _launch_uri(uri: str) -> tuple[bool, str]:
    """Launch a `steam://` URI via the OS shell. Returns (ok, detail)."""
    try:
        await asyncio.to_thread(os.startfile, uri)
        log.info("steam_launch_ok", uri=uri)
        return True, uri
    except OSError as exc:
        log.warning("steam_launch_fail", uri=uri, error=str(exc))
        return False, f"os error: {exc}"


async def _handle(event: ActionRequested) -> ActionCompleted | None:
    action = event.action
    params = event.params or {}

    if action == "steam_open":
        ok, detail = await _launch_uri("steam://open/main")
        return ActionCompleted(
            request_id=event.request_id, action=action, ok=ok, detail=detail
        )

    if action == "steam_launch_game":
        app_id = params.get("app_id")
        name = params.get("name")
        if not isinstance(app_id, int):
            if isinstance(name, str) and name.strip():
                looked_up = _lookup_app_id(name)
                if looked_up is None:
                    detail = f"unknown game: {name}"
                    log.info("steam_unknown_game", name=name)
                    return ActionCompleted(
                        request_id=event.request_id,
                        action=action,
                        ok=False,
                        detail=detail,
                    )
                app_id = looked_up
            else:
                return ActionCompleted(
                    request_id=event.request_id,
                    action=action,
                    ok=False,
                    detail="missing app_id or name",
                )
        uri = f"steam://rungameid/{app_id}"
        ok, detail = await _launch_uri(uri)
        return ActionCompleted(
            request_id=event.request_id, action=action, ok=ok, detail=detail
        )

    return None  # not ours — ignore


async def run_steam_service(bus: Bus, settings: Settings) -> None:
    """Subscribe to ActionRequested and launch Steam URIs for steam_* actions."""
    log.info("steam_service_start", aliases=len(STEAM_ALIASES))
    async with bus.stream(ActionRequested) as q:
        try:
            while True:
                event = await q.get()
                result = await _handle(event)
                if result is not None:
                    await bus.publish(result)
        except asyncio.CancelledError:
            log.info("steam_service_cancelled")
            raise
