# 🏗️ Architecture

> **Status:** Phase 1 + 2 implemented; later phases will extend this map. Every service below is a long-running `async def run_*_service(bus, settings, …)` coroutine wired into a single `asyncio.TaskGroup` in `src/kobe/__main__.py`.

---

## System Layers

KOBE is built as **six coordinated layers**, each with a clean boundary:

```
┌─────────────────────────────────────────────────────────────┐
│                        PROJECT KOBE                         │
├────────────────┬────────────────────────────────────────────┤
│  Layer 1       │  Wake Layer          OpenWakeWord          │
│  Layer 2       │  Voice Layer         STT + TTS             │
│  Layer 3       │  Brain Layer         OpenClaw + Claude     │
│  Layer 4       │  Execution Layer     PC automation         │
│  Layer 5       │  Visual Layer        HUD frontend/backend  │
│  Layer 6       │  Peripheral Layer    Printer, Spotify, etc │
└────────────────┴────────────────────────────────────────────┘
```

---

## Module Map

```
[Mic]
  └─→ wake_service
        └─→ stt_service
              └─→ conversation_router ←── screen_vision_service
                        │               ←── gesture_service
                        ▼
                [Claude / OpenClaw]
                        │
                        ▼
                  action_executor
                  ├── app_automation
                  ├── printer_integration
                  ├── spotify_integration
                  ├── steam_integration
                  ├── discord_alerts
                  └── confirmation_manager
                        │
                        ▼
                   tts_service → [Speakers]
                        │
                        ▼
                   hud_backend → hud_frontend → [HUD Display]
```

---

## Data Flow

```
User speaks
    ↓
wake_service detects "Hey KOBE"
    ↓
stt_service transcribes audio → text
    ↓
conversation_router sends to Claude via OpenClaw
    ↓
Claude generates response + action intent
    ↓
action_executor performs action
    ↓
tts_service speaks response
    ↓
hud_backend updates display
```

---

## Modules

| Module | Path | Purpose | Phase | Status |
|--------|------|---------|-------|--------|
| `bus` | `src/kobe/bus.py` | Asyncio pub/sub with drop-oldest overflow | 1 | ✅ |
| `events` | `src/kobe/events.py` | Immutable dataclass event types | 1 | ✅ |
| `config` | `src/kobe/config.py` | pydantic-settings, layered env-file resolution | 1 | ✅ |
| `audio` | `src/kobe/audio.py` | Single-owner mic source; thread-safe fan-out + 5 s pre-roll | 1 | ✅ |
| `wake_service` | `src/kobe/wake/service.py` | OpenWakeWord detection; suppresses during mute / speak / record | 1 | ✅ |
| `stt_service` | `src/kobe/stt/service.py` | faster-whisper + RMS-energy VAD | 1 | ✅ |
| `tts_service` | `src/kobe/tts/service.py` | ElevenLabs → OpenAI; barge-in gated on speaking state | 1 | ✅ |
| `brain/router` | `src/kobe/brain/router.py` | HTTP POST to OpenClaw; echo stub when unconfigured | 1 | ✅ |
| `action_executor` | `src/kobe/actions/executor.py` | open_app / open_url / noop (extensible) | 1 | ✅ |
| `mute_service` | `src/kobe/mute/service.py` | Global keyboard hotkey → MuteToggled + InterruptRequested | 1 | ✅ |
| `hud_backend` | `src/kobe/hud/backend.py` | FastAPI + WebSocket; single outbound writer, per-client lock | 2 | ✅ |
| `hud_frontend` | `src/kobe/hud/static/` | Plain HTML/CSS/JS dashboard, CSS-animated state orb | 2 | ✅ |
| `system_status` | `src/kobe/system/status.py` | psutil + pygetwindow telemetry | 2 | ✅ |
| `printer_integration` | `src/kobe/integrations/bambu.py` | Bambu P1S LAN MQTT (paho-mqtt v2), status + pause/resume/cancel | 3 | ✅ |
| `spotify_integration` | `src/kobe/integrations/spotify.py` | spotipy play/pause/next/prev/volume + now-playing polling | 3 | ✅ |
| `steam_integration` | `src/kobe/integrations/steam.py` | `steam://` URI launcher with name→app_id alias map | 3 | ✅ |
| `discord_alerts` | `src/kobe/integrations/discord.py` | Webhook poster on `PrinterAlert`, 3 s dedupe | 3 | ✅ |
| `windows_automation` | `src/kobe/automation/windows_ctrl.py` | pycaw volume + pygetwindow focus/min/max + win+d | 3 | ✅ |
| `confirmation_manager` | `src/kobe/actions/confirmation.py` | Destructive-action yes/no voice challenge, sequential | 3 | ✅ |
| `vision_service` | `src/kobe/vision/service.py` | Captures the screen on `screen_inspect` action or `VisionRequested` event, runs a pluggable `VisionBackend`, publishes `VisionResult` + `ResponseReady`. Phase 4 foundation ships only the `NullBackend` stub. | 4 | 🟡 foundation |
| `vision_capture` | `src/kobe/vision/capture.py` | mss-based screenshot for foreground/full/region. region requires a valid box (no silent widening). | 4 | ✅ |
| `vision_backends` | `src/kobe/vision/backends.py` | `VisionBackend` Protocol + `build_backend(settings)` factory. Real backends (OpenClaw, OpenAI, Moondream) come later. | 4 | 🟡 |
| `gesture_service` | `src/kobe/gestures/` | Webcam hand tracking | 5 | 🔲 |
| `profile_manager` | `src/kobe/profiles/` | User profiles (Lambert, future Jasmine) | 6 | 🔲 |

## Event catalogue (Phase 1 + 2)

| Event | Published by | Consumed by |
|-------|--------------|-------------|
| `WakeDetected` | wake | stt, tts (barge-in), hud |
| `RecordingStarted` / `RecordingStopped` | stt | wake (suppression), hud |
| `TranscriptReady` | stt | brain, hud |
| `ResponseReady` | brain | tts, hud |
| `ActionRequested` | brain | actions, hud |
| `ActionCompleted` | actions | hud |
| `SpeakStarted` / `SpeakFinished` | tts | wake (suppression), hud |
| `InterruptRequested` | mute | tts |
| `MuteToggled` | mute | wake, hud |
| `SystemStatus` | system | hud |
| `PrinterStatus` | bambu | hud (cache + relay) |
| `PrinterAlert` | bambu | discord, hud (relay) |
| `NowPlayingChanged` | spotify | hud (cache + relay) |
| `ConfirmationRequested` | brain (when action is destructive) | confirmation, hud (relay) |
| `ConfirmationResult` | confirmation | hud (relay) |
| `VisionRequested` | brain (or any caller) | vision_service |
| `VisionResult` | vision_service | hud (relay) |

---

## Design Principles

- **Modular** — clean boundaries, replaceable providers
- **Local-first** — STT, wake, gestures all run on-device
- **Config-driven** — behaviour controlled via config files
- **Event-driven** — HUD and alerts driven by an internal event bus
- **Confirmation layer** — destructive/irreversible actions always require confirm
- **Provider-agnostic TTS/STT** — swappable without rewriting core

---

*Full architecture spec to be generated in Claude Code before Phase 1 implementation begins.*
