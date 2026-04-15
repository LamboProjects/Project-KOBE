# 🖥️ HUD

> **Phase 2** · Status: 🔲 Not started

Always-on second monitor display — KOBE's persistent visual presence.

---

## Responsibilities

- Render a fullscreen, always-on interface on the dedicated second monitor
- Display KOBE's current state and active context at a glance
- Show live voice transcripts and responses
- Surface printer, media, and system status widgets
- Handle gesture input from `gesture_service`

## Architecture

```
hud_backend (Node/Python service)
    ├── subscribes to internal event bus
    ├── aggregates state from all services
    └── serves data to hud_frontend via WebSocket

hud_frontend (local web app or Electron)
    ├── fullscreen kiosk-mode UI
    ├── always-on second monitor
    └── renders widgets from hud_backend data
```

## Visual Design

| Property | Value |
|----------|-------|
| Background | Near-black (`#0a0e1a`) |
| Primary colour | Cyan (`#00D4FF`) |
| Accent | Blue (`#1a6eff`) |
| Alert colour | Amber (`#FF9500`) |
| Error colour | Red (`#FF3B30`) |
| Font | Fira Code / JetBrains Mono |
| Theme | Holographic, futuristic, clean — not gimmicky |

## Core Modules

### Always Visible
- 🕐 Current time and date
- 🎙️ KOBE state badge — `IDLE` / `LISTENING` / `THINKING` / `SPEAKING` / `MUTED`
- 🔊 Mic status indicator
- 🖨️ Printer quick status
- 🎵 Spotify now playing

### Contextual (appear when relevant)
- 📝 Live voice transcript
- 💬 KOBE response panel
- 🖨️ Full printer dashboard
- ✅ Confirmation prompt overlay
- 👋 Gesture hint overlay
- 🔍 Screen analysis result panel

## Notes

- Phase 2: start as a **local web app** (fastest to prototype and iterate)
- Phase 6: convert to **Electron** for better kiosk behaviour if needed
- Must be readable from desk distance — large text, high contrast
- Idle mode: animated but subdued — alive without being distracting
