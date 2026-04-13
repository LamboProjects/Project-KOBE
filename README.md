# Project KOBE
### Keeping Order & Being Efficient

> A desk-based, voice-first AI assistant inspired by JARVIS — built for real daily use.

---

## Overview

KOBE is a Windows-based personal AI command center that operates through three layers:

- **Voice** — wake-word activated, natural conversation, barge-in supported
- **Visual HUD** — always-on second monitor display with live status and context
- **Control Layer** — app automation, printer control, media control, gestures

Built on OpenClaw + Claude, with local STT (faster-whisper on RTX 3060) and ElevenLabs TTS.

---

## Status

| Phase | Name | Status |
|-------|------|--------|
| Phase 1 | Core Voice MVP | 🔲 Planned |
| Phase 2 | HUD MVP | 🔲 Planned |
| Phase 3 | Productivity & Printer Integration | 🔲 Planned |
| Phase 4 | Screen Vision & Context Awareness | 🔲 Planned |
| Phase 5 | Gesture Control | 🔲 Planned |
| Phase 6 | Premium Polish | 🔲 Planned |
| Phase 7 | Holographic Fan Integration | 🔲 Planned |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Wake Word | OpenWakeWord |
| STT | faster-whisper (local, RTX 3060) |
| Brain | OpenClaw + Claude Sonnet |
| TTS | ElevenLabs (primary), OpenAI TTS (backup) |
| HUD | Local web app → Electron |
| Gestures | MediaPipe Hands + webcam |
| Printer | Bambu Lab P1S (local + cloud) |
| Alerts | Discord |

---

## Hardware

- **PC:** Windows desktop, RTX 3060
- **Monitors:** Dual — one dedicated KOBE HUD display
- **Audio:** USB microphone + dedicated speakers
- **Camera:** Logitech C922 (gesture tracking)
- **Printer:** Bambu Lab P1S

---

## Integrations

- Spotify
- Steam
- VS Code
- Bambu Studio / P1S printer
- FreeCAD
- Discord
- Smart plug (future: smart lights + home devices)

---

## Docs

| Document | Description |
|----------|-------------|
| [Detailed Spec](./docs/Project%20KOBE%20-%20Detailed%20Spec.md) | Full planning spec and phased roadmap |
| [Voice Assistant Plan](./docs/Project%20KOBE%20-%20Voice%20Assistant%20Plan.md) | Voice pipeline options and quick-start plan |
| [Architecture](./docs/ARCHITECTURE.md) | System architecture (coming soon) |
| [Roadmap](./ROADMAP.md) | Phased build roadmap |

---

## Repo Structure

```
Project-KOBE/
├── docs/               # Planning docs, specs, architecture
├── src/                # Source code (populated per phase)
│   ├── wake/           # Wake word service
│   ├── stt/            # Speech-to-text service
│   ├── tts/            # Text-to-speech service
│   ├── brain/          # Conversation router + OpenClaw bridge
│   ├── hud/            # HUD frontend + backend
│   ├── integrations/   # Spotify, Steam, Bambu, Discord, etc.
│   ├── automation/     # PC automation + app control
│   ├── gestures/       # Gesture recognition service
│   └── vision/         # Screen vision service
├── config/             # Configuration files
├── assets/             # Icons, fonts, visual assets
├── scripts/            # Setup and utility scripts
├── tests/              # Tests per module
├── .github/            # GitHub Actions workflows
├── ROADMAP.md          # Phased roadmap
├── CONTRIBUTING.md     # Contribution guidelines
└── README.md           # This file
```

---

## Getting Started

> ⚠️ Project is currently in planning phase. Implementation begins in Phase 1.

Setup instructions will be added as each phase is completed.

---

## License

Private repository — all rights reserved.
