# 🖥️ HUD

> **Phase 2** · Status: ✅ Built

Always-on second monitor display — KOBE's persistent visual presence. Single-page web app served locally at `http://127.0.0.1:8765`.

---

## What's built

- `backend.py` — `run_hud_service(bus, settings)` spins up FastAPI + uvicorn on `127.0.0.1:8765`. Routes:
  - `GET /` — serves `static/index.html`
  - `GET /static/*` — serves `static/app.js`, `static/style.css`
  - `GET /health` — liveness JSON
  - `GET /ws` — WebSocket with a per-client `asyncio.Lock` and single outbound writer, hydrating a `HudSnapshot` on connect.
- Subscribes to every bus event (`WakeDetected`, `TranscriptReady`, `ResponseReady`, `ActionCompleted`, `SpeakStarted/Finished`, `MuteToggled`, `SystemStatus`, `PrinterStatus`, `PrinterAlert`, `NowPlayingChanged`, `ConfirmationRequested/Result`, `VisionResult`, `GestureDetected`, `WebcamStatus`) and fans them out after stripping server-local paths (e.g. vision `image_path`).
- `static/` — `index.html`, `app.js`, `style.css`. Plain vanilla JS, CSS-animated state orb, scanline + vignette overlays. State derived server-side from event history.

## Visual design

| Property | Value |
|----------|-------|
| Background | Near-black (`#0a0e1a`) |
| Primary colour | Cyan (`#00D4FF`) |
| Accent | Blue (`#1a6eff`) |
| Alert colour | Amber (`#FF9500`) |
| Error colour | Red (`#FF3B30`) |
| Font | JetBrains Mono |
| Theme | Holographic, futuristic, clean — not gimmicky |

## Panels

### Always visible
- Clock, foreground app, CPU / memory
- KOBE state badge — `IDLE` / `LISTENING` / `THINKING` / `SPEAKING` / `MUTED`
- Mic + mute indicator
- Printer quick status
- Spotify now-playing

### Contextual
- Live voice transcript (last 8, hydrated on reconnect)
- KOBE response panel
- Full printer dashboard (progress / stage / temps / AMS)
- Confirmation prompt overlay
- Vision result panel with `SCANNING…` shimmer (45 s safety timeout)
- Gesture + webcam health indicator

## Notes

- Kiosk launch: `start chrome --kiosk http://127.0.0.1:8765`
- Electron migration (Phase 6) still planned for tighter kiosk behaviour
- No camera frames or hand landmarks ever hit the HUD — only semantic gesture names + confidences
