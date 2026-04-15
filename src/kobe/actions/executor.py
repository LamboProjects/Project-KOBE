"""Action executor — dispatches ActionRequested events to concrete handlers.

Phase 1 supports launching apps, opening URLs, and a noop. All shell/filesystem
calls are pushed through `asyncio.to_thread` so the event loop never blocks.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import webbrowser
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested

log = structlog.get_logger(__name__)


# Windows-friendly alias map. Values are either:
#   - a URI scheme string (Spotify, Steam) passed to os.startfile
#   - a command name on PATH (code.cmd, chrome, firefox, notepad)
# Keys are lowercased for case-insensitive lookup.
_APP_ALIASES: dict[str, str] = {
    "vs code": "code.cmd",
    "vscode": "code.cmd",
    "code": "code.cmd",
    "spotify": "spotify:",
    "steam": "steam://open/main",
    "chrome": "chrome",
    "firefox": "firefox",
    "notepad": "notepad",
    "explorer": "explorer",
    "calculator": "calc",
    "calc": "calc",
}


def _launch_with_path(path: str) -> None:
    """Blocking launch via os.startfile (Windows shell associations)."""
    os.startfile(path)  # type: ignore[attr-defined]


def _launch_with_alias(target: str) -> None:
    """Blocking launch via os.startfile for URIs, else through the shell."""
    # URI schemes (spotify:, steam://...) work with os.startfile.
    if "://" in target or target.endswith(":"):
        os.startfile(target)  # type: ignore[attr-defined]
        return
    # Plain command — try os.startfile first (handles .exe / shell verbs for
    # known apps like `notepad`, `calc`, `explorer`). Fall back to an
    # explicitly-quoted `cmd /c start` if that fails.
    try:
        os.startfile(target)  # type: ignore[attr-defined]
    except OSError:
        _launch_fallback(target)


def _launch_fallback(name: str) -> None:
    """Last-ditch: `cmd /c start "" "<name>"` with explicit quoting for names with spaces."""
    # Escape embedded double-quotes, wrap in quotes. `start ""` eats the title arg.
    safe = name.replace('"', r'\"')
    subprocess.Popen(
        f'cmd /c start "" "{safe}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _open_app(params: dict[str, Any]) -> tuple[bool, str]:
    name = str(params.get("name", "")).strip()
    path = params.get("path")

    if path:
        try:
            await asyncio.to_thread(_launch_with_path, str(path))
            return True, f"launched path: {path}"
        except Exception as exc:  # noqa: BLE001
            log.warning("open_app_path_failed", path=path, error=str(exc))
            # fall through to alias / fallback using name

    if not name:
        return False, "open_app requires 'name' or 'path'"

    alias = _APP_ALIASES.get(name.lower())
    if alias is not None:
        try:
            await asyncio.to_thread(_launch_with_alias, alias)
            return True, f"launched alias: {name} -> {alias}"
        except Exception as exc:  # noqa: BLE001
            log.warning("open_app_alias_failed", name=name, alias=alias, error=str(exc))

    # Generic fallback: `start "" <name>`
    try:
        await asyncio.to_thread(_launch_fallback, name)
        return True, f"launched via shell: {name}"
    except Exception as exc:  # noqa: BLE001
        return False, f"open_app failed: {exc}"


async def _open_url(params: dict[str, Any]) -> tuple[bool, str]:
    url = str(params.get("url", "")).strip()
    if not url:
        return False, "open_url requires 'url'"
    try:
        ok = await asyncio.to_thread(webbrowser.open, url)
        if ok:
            return True, f"opened url: {url}"
        return False, f"webbrowser.open returned False for {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"open_url failed: {exc}"


async def _noop(_params: dict[str, Any]) -> tuple[bool, str]:
    return True, "noop"


_HANDLERS = {
    "open_app": _open_app,
    "open_url": _open_url,
    "noop": _noop,
}


async def _dispatch(event: ActionRequested) -> ActionCompleted:
    handler = _HANDLERS.get(event.action)
    if handler is None:
        log.warning("unknown_action", action=event.action, request_id=event.request_id)
        return ActionCompleted(
            request_id=event.request_id,
            action=event.action,
            ok=False,
            detail=f"unknown action: {event.action}",
        )
    try:
        ok, detail = await handler(event.params or {})
    except Exception as exc:  # noqa: BLE001
        log.exception("action_handler_crashed", action=event.action)
        ok, detail = False, f"handler crashed: {exc}"
    return ActionCompleted(
        request_id=event.request_id,
        action=event.action,
        ok=ok,
        detail=detail,
    )


async def run_action_executor(bus: Bus, settings: Settings) -> None:
    """Long-running coroutine: consumes ActionRequested, publishes ActionCompleted."""
    log.info("action_executor_start", hotkey=settings.mute_hotkey)
    async with bus.stream(ActionRequested) as queue:
        try:
            while True:
                event = await queue.get()
                log.info(
                    "action_requested",
                    request_id=event.request_id,
                    action=event.action,
                    params=event.params,
                )
                result = await _dispatch(event)
                log.info(
                    "action_completed",
                    request_id=result.request_id,
                    action=result.action,
                    ok=result.ok,
                    detail=result.detail,
                )
                await bus.publish(result)
        except asyncio.CancelledError:
            log.info("action_executor_stop")
            raise
