"""Phase 2 smoke test.

Start the HUD backend + system-status service for ~4 seconds, hit the HTTP
endpoints, and connect a WebSocket client. Confirms routing, static assets,
snapshot frame, and event broadcast are wired end-to-end. No API keys needed.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx
import structlog

from kobe.bus import Bus
from kobe.config import load_settings
from kobe.events import (
    MuteToggled,
    RecordingStarted,
    ResponseReady,
    TranscriptReady,
)
from kobe.logging import configure_logging


async def _hit(client: httpx.AsyncClient, url: str) -> tuple[int, int]:
    r = await client.get(url)
    return r.status_code, len(r.content)


async def main() -> int:
    configure_logging("INFO")
    log = structlog.get_logger("smoke2")

    settings = load_settings()
    # Use an ephemeral port to avoid conflicts.
    settings.hud_port = 18765
    settings.hud_host = "127.0.0.1"

    bus = Bus()

    from kobe.hud.backend import run_hud_server
    from kobe.system.status import run_system_status_service

    hud_task = asyncio.create_task(run_hud_server(bus, settings))
    status_task = asyncio.create_task(run_system_status_service(bus, settings))

    # Wait for the server to come up.
    base = f"http://{settings.hud_host}:{settings.hud_port}"
    async with httpx.AsyncClient(timeout=2.0) as client:
        for _ in range(30):
            try:
                await client.get(f"{base}/health")
                break
            except Exception:
                await asyncio.sleep(0.1)
        else:
            log.error("hud_never_started")
            return 1

        # Hit the three critical routes.
        health = await _hit(client, f"{base}/health")
        index = await _hit(client, f"{base}/")
        css = await _hit(client, f"{base}/static/style.css")
        js = await _hit(client, f"{base}/static/app.js")
        log.info("http_probe", health=health, index=index, css=css, js=js)
        assert health[0] == 200, f"/health: {health}"
        assert index[0] == 200 and index[1] > 0, f"/: {index}"
        assert css[0] == 200 and css[1] > 0, f"/static/style.css: {css}"
        assert js[0] == 200 and js[1] > 0, f"/static/app.js: {js}"

    # Connect a WebSocket client, expect a snapshot frame + broadcast frames.
    import websockets

    ws_url = f"ws://{settings.hud_host}:{settings.hud_port}/ws"
    async with websockets.connect(ws_url, open_timeout=3.0) as ws:
        snap = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        log.info("snapshot_frame", type=snap.get("type"), state=snap.get("state"))
        assert snap["type"] == "HudSnapshot", f"expected HudSnapshot, got {snap['type']}"

        # Drive events and check we see them.
        seen: list[str] = []
        await bus.publish(MuteToggled(muted=False))  # ensure not muted
        await bus.publish(RecordingStarted(request_id="s1"))
        await bus.publish(TranscriptReady(request_id="s1", text="hello hud", duration_s=0.5))
        await bus.publish(ResponseReady(request_id="s1", text="hi from kobe"))

        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline and len(seen) < 6:
            try:
                msg = json.loads(
                    await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - asyncio.get_running_loop().time()))
                )
            except asyncio.TimeoutError:
                break
            seen.append(msg["type"])
        log.info("ws_events_seen", types=seen)
        for expected in ("RecordingStarted", "TranscriptReady", "ResponseReady"):
            assert expected in seen, f"missing {expected} in {seen}"

    hud_task.cancel()
    status_task.cancel()
    for t in (hud_task, status_task):
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    log.info("smoke_phase2_ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
