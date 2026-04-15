"""HUD backend — FastAPI app streaming bus events to the browser via WebSocket.

The service subscribes to every event type defined in :mod:`kobe.events`, derives
a coarse "HUD state" from the stream (idle / listening / thinking / speaking /
muted), and fans the events out as JSON to any connected WS clients.

Write path: each per-event-type consumer task pushes a rendered payload onto a
single `asyncio.Queue`. One dedicated writer task drains that queue and sends
each payload to every connected client *serially per client, in parallel across
clients*. Serializing per client prevents frame interleaving on a single WS
(starlette's WebSocket is not safe under concurrent `send_json`); fanning out
in parallel keeps one slow client from blocking everyone else.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from kobe import events as kevents
from kobe.bus import Bus
from kobe.config import Settings

log = structlog.get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_MAX_TRANSCRIPT_CACHE = 8
_SEND_TIMEOUT_S = 2.0

# Every dataclass event we relay. Keep this explicit so the HUD stays in lock-step
# with the event module rather than relying on reflection.
_EVENT_TYPES: tuple[type, ...] = (
    kevents.WakeDetected,
    kevents.RecordingStarted,
    kevents.RecordingStopped,
    kevents.TranscriptReady,
    kevents.ResponseReady,
    kevents.ActionRequested,
    kevents.ActionCompleted,
    kevents.SpeakStarted,
    kevents.SpeakFinished,
    kevents.InterruptRequested,
    kevents.MuteToggled,
    kevents.SystemStatus,
    # Phase 3
    kevents.PrinterStatus,
    kevents.PrinterAlert,
    kevents.NowPlayingChanged,
    kevents.ConfirmationRequested,
    kevents.ConfirmationResult,
    # Phase 4 foundation
    kevents.VisionRequested,
    kevents.VisionResult,
)


def _derive_state(current: str, event: object) -> str:
    """Update the derived HUD state given a new event.

    Mute is sticky: once muted, most transitions are suppressed until unmute.
    On unmute we only reset to idle if we were previously muted — we don't clobber
    an otherwise-current state that might have been delivered while muted.
    """
    if isinstance(event, kevents.MuteToggled):
        if event.muted:
            return "muted"
        return "idle" if current == "muted" else current
    if current == "muted":
        return "muted"
    if isinstance(event, kevents.WakeDetected):
        return "listening"
    if isinstance(event, kevents.RecordingStarted):
        return "listening"
    if isinstance(event, kevents.RecordingStopped):
        return "thinking"
    if isinstance(event, kevents.TranscriptReady):
        return "thinking"
    if isinstance(event, kevents.SpeakStarted):
        return "speaking"
    if isinstance(event, kevents.SpeakFinished):
        return "idle"
    return current


async def run_hud_server(bus: Bus, settings: Settings) -> None:
    if settings.hud_enabled is False:
        log.info("hud_disabled")
        return

    app = FastAPI(title="KOBE HUD")

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    clients: dict[WebSocket, asyncio.Lock] = {}
    state: dict[str, str] = {"value": "idle"}
    transcript_cache: deque[dict[str, Any]] = deque(maxlen=_MAX_TRANSCRIPT_CACHE)
    last_response: dict[str, Any] | None = None
    last_system: dict[str, Any] | None = None
    last_printer: dict[str, Any] | None = None
    last_now_playing: dict[str, Any] | None = None
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)

    def snapshot() -> dict[str, Any]:
        data: dict[str, Any] = {
            "transcript": list(transcript_cache),
            "response": last_response,
            "system": last_system,
            "printer": last_printer,
            "now_playing": last_now_playing,
        }
        return {"type": "HudSnapshot", "data": data, "state": state["value"]}

    async def _send_one(ws: WebSocket, payload: dict[str, Any]) -> bool:
        """Send to a single client with a per-client lock + timeout."""
        lock = clients.get(ws)
        if lock is None:
            return False
        try:
            async with lock:
                await asyncio.wait_for(ws.send_json(payload), timeout=_SEND_TIMEOUT_S)
            return True
        except Exception:
            return False

    async def _reaper(dead: list[WebSocket]) -> None:
        for ws in dead:
            clients.pop(ws, None)
            try:
                await ws.close()
            except Exception:
                pass

    async def _writer() -> None:
        """Single outbound writer; fans each payload to every client in parallel."""
        while True:
            payload = await outbound.get()
            if not clients:
                continue
            targets = list(clients.keys())
            results = await asyncio.gather(
                *(_send_one(ws, payload) for ws in targets),
                return_exceptions=False,
            )
            dead = [ws for ws, ok in zip(targets, results) if not ok]
            if dead:
                await _reaper(dead)

    def enqueue(payload: dict[str, Any]) -> None:
        """Drop-oldest if the outbound queue ever backs up."""
        try:
            outbound.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                outbound.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                outbound.put_nowait(payload)
            except asyncio.QueueFull:
                return

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "connected_clients": len(clients)}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        clients[ws] = asyncio.Lock()
        log.info("client_connected", total=len(clients))
        try:
            # Send the snapshot directly, not through the broadcast queue,
            # so a fresh client sees hydration before any newer broadcasts.
            lock = clients[ws]
            async with lock:
                await ws.send_json(snapshot())
            while True:
                # We don't expect inbound messages; reading keeps the
                # connection honest and surfaces disconnects promptly.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("ws_error", error=str(exc))
        finally:
            clients.pop(ws, None)
            log.info("client_disconnected", total=len(clients))

    # Subscribe to every event type up front so publishers never race us.
    subscriptions: list[tuple[type, asyncio.Queue]] = [
        (et, bus.subscribe(et)) for et in _EVENT_TYPES
    ]

    async def _consume(event_type: type, q: asyncio.Queue) -> None:
        nonlocal last_response, last_system, last_printer, last_now_playing
        name = event_type.__name__
        while True:
            event = await q.get()
            try:
                data = asdict(event)
            except TypeError:
                # Defensive: non-dataclass event slipped through.
                data = getattr(event, "__dict__", {})

            # Cache selected recent-history items so reconnecting clients get hydration.
            if isinstance(event, kevents.TranscriptReady):
                transcript_cache.appendleft({"text": event.text, "request_id": event.request_id})
            elif isinstance(event, kevents.ResponseReady):
                last_response = {"text": event.text, "request_id": event.request_id}
            elif isinstance(event, kevents.SystemStatus):
                last_system = data
            elif isinstance(event, kevents.PrinterStatus):
                last_printer = data
            elif isinstance(event, kevents.NowPlayingChanged):
                last_now_playing = data

            state["value"] = _derive_state(state["value"], event)
            enqueue({"type": name, "data": data, "state": state["value"]})

    config = uvicorn.Config(
        app=app,
        host=settings.hud_host,
        port=settings.hud_port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    # Prevent uvicorn from hijacking signal handlers — the parent TaskGroup owns shutdown.
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    log.info("server_start", host=settings.hud_host, port=settings.hud_port)

    consumer_tasks: list[asyncio.Task] = []
    writer_task: asyncio.Task | None = None
    server_task: asyncio.Task | None = None
    try:
        consumer_tasks = [
            asyncio.create_task(_consume(et, q), name=f"hud-consume-{et.__name__}")
            for et, q in subscriptions
        ]
        writer_task = asyncio.create_task(_writer(), name="hud-writer")
        server_task = asyncio.create_task(server.serve(), name="hud-uvicorn")
        # Block until cancelled; surface server-task crashes early.
        await server_task
    except asyncio.CancelledError:
        pass
    finally:
        # Signal uvicorn to exit and wait for it.
        server.should_exit = True
        if server_task is not None:
            try:
                await asyncio.wait_for(server_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                server_task.cancel()
                try:
                    await server_task
                except BaseException:
                    pass

        # Stop internal tasks.
        tasks_to_cancel = list(consumer_tasks)
        if writer_task is not None:
            tasks_to_cancel.append(writer_task)
        for t in tasks_to_cancel:
            t.cancel()
        for t in tasks_to_cancel:
            try:
                await t
            except BaseException:
                pass

        # Close any lingering WS clients.
        for ws in list(clients.keys()):
            try:
                await ws.close()
            except Exception:
                pass
        clients.clear()

        # Unsubscribe from the bus.
        for event_type, q in subscriptions:
            bus.unsubscribe(event_type, q)

        log.info("server_stopped")
