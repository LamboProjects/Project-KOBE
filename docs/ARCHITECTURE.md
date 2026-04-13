# 🏗️ Architecture

> **Status:** Stub — full architecture to be generated via Claude Code using the prompt in [docs/Project KOBE - Detailed Spec.md](./Project%20KOBE%20-%20Detailed%20Spec.md) (Section 26).

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

| Module | Purpose | Phase |
|--------|---------|-------|
| `wake_service` | Always-on wake word detection | 1 |
| `stt_service` | Speech-to-text (faster-whisper) | 1 |
| `tts_service` | Text-to-speech (ElevenLabs) | 1 |
| `conversation_router` | Routes input to Claude, returns response | 1 |
| `action_executor` | Dispatches actions to integrations | 1 |
| `hud_backend` | Event bus → HUD data layer | 2 |
| `hud_frontend` | Always-on second monitor UI | 2 |
| `printer_integration` | Bambu P1S status + control | 3 |
| `spotify_integration` | Playback control | 3 |
| `steam_integration` | Game launching | 3 |
| `discord_alerts` | Printer/event notifications | 3 |
| `confirmation_manager` | Destructive action confirmation | 3 |
| `screen_vision_service` | On-demand screen analysis | 4 |
| `gesture_service` | Webcam hand tracking | 5 |
| `settings/profile_manager` | User profiles (Lambert, future Jasmine) | 6 |

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
