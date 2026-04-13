# Architecture

> ⚠️ This document will be populated after Phase 1 planning is complete.

## System Layers

KOBE is designed as six coordinated layers:

1. **Wake Layer** — OpenWakeWord, always-on listening
2. **Voice Layer** — faster-whisper STT + ElevenLabs TTS
3. **Brain Layer** — OpenClaw + Claude, conversation routing
4. **Execution Layer** — PC automation, app control, integrations
5. **Visual Layer** — HUD frontend + backend on second monitor
6. **Peripheral Layer** — Printer, Spotify, Steam, Discord, gestures

## Module Map

```
wake_service → stt_service → conversation_router → tts_service
                                    ↓
                           action_executor
                           ├── app_automation
                           ├── printer_integration
                           ├── spotify_integration
                           ├── steam_integration
                           └── discord_alerts

hud_backend ←─────────────── all services (event bus)
hud_frontend ← hud_backend

gesture_service ──────────→ conversation_router / hud_frontend
screen_vision_service ────→ conversation_router
confirmation_manager ←───── action_executor
```

## Data Flow

```
[Mic] → wake_service → stt_service → conversation_router
                                            ↓
                                    [Claude / OpenClaw]
                                            ↓
                                     action_executor
                                            ↓
                               tts_service → [Speakers]
                                            ↓
                                      hud_backend → [HUD Display]
```

---

Full architecture spec to be generated via Claude Code using the planning prompt in `docs/Project KOBE - Detailed Spec.md` (Section 26).
