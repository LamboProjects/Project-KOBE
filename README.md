<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=32&pause=1000&color=00D4FF&center=true&vCenter=true&width=600&lines=Project+KOBE;Keeping+Order+%26+Being+Efficient;Your+Personal+JARVIS" alt="Typing SVG" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Phase%203%20Complete-00D4FF?style=for-the-badge&logo=github" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows" />
  <img src="https://img.shields.io/badge/GPU-NVIDIA%20CUDA-76B900?style=for-the-badge&logo=nvidia" />
  <img src="https://img.shields.io/badge/AI-Claude%20Sonnet-8A2BE2?style=for-the-badge&logo=anthropic" />
  <img src="https://img.shields.io/badge/TTS-ElevenLabs-FF6B35?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-Private-red?style=for-the-badge" />
</p>

<p align="center">
  <i>A desk-based, voice-first AI assistant inspired by JARVIS — built for real daily use.</i>
</p>

---

## 🧠 What is KOBE?

**KOBE** (Keeping Order & Being Efficient) is a Windows-based personal AI command center that lives at your desk and feels genuinely alive. Wake word activated, voice-first, with an always-on HUD on a dedicated second monitor.

Not a chatbot with a mic duct-taped on. A **real operating layer** over your digital environment.

```
"Hey KOBE, how's my print doing?"
"Hey KOBE, open VS Code."
"OK KOBE, pause the print."
"Hey KOBE, what's on my screen?"
```

---

## ⚡ Core Capabilities

| Layer | Technology | Status |
|-------|-----------|--------|
| 🎤 **Wake Word** | OpenWakeWord — `hey_jarvis` stand-in until custom "Hey KOBE" trained | ✅ Built |
| 🗣️ **Speech-to-Text** | faster-whisper `base.en` on CUDA, int8_float16 | ✅ Built |
| 🧠 **Intelligence** | OpenClaw HTTP (echo stub when unconfigured) | ✅ Built |
| 🔊 **Text-to-Speech** | ElevenLabs primary, OpenAI TTS fallback, barge-in | ✅ Built |
| 🖥️ **HUD** | FastAPI + WebSocket + vanilla-JS dashboard @ `127.0.0.1:8765` | ✅ Built |
| 🖨️ **Printer** | Bambu Lab P1S over LAN MQTT (paho-mqtt v2) with HUD widget + Discord alerts | ✅ Built |
| 🎵 **Media** | Spotify (spotipy, play/pause/next/prev/vol + now-playing) and Steam `steam://` launcher | ✅ Built |
| 🖥️ **Windows** | System volume via pycaw, window focus/min/max via pygetwindow, show-desktop | ✅ Built |
| 🛑 **Safety** | Confirmation flow for destructive actions (yes/no voice challenge before cancel/pause) | ✅ Built |
| 👋 **Gestures** | MediaPipe + Logitech C922 | 🔲 Planned (Phase 5) |
| 👁️ **Screen Vision** | mss capture + pluggable `VisionBackend` (NullBackend stub today) | 🟡 Foundation built (Phase 4) |
| ✨ **Holo Fan** | 65cm holographic ambient display | 🔲 Planned (Phase 7) |

---

## 🗺️ Roadmap at a Glance

```
Phase 1 ──── Core Voice MVP          ✅
Phase 2 ──── HUD Display             ✅
Phase 3 ──── Printer & Productivity  ✅
Phase 4 ──── Screen Vision           🔲
Phase 5 ──── Gesture Control         🔲
Phase 6 ──── Premium Polish          🔲
Phase 7 ──── Holographic Fan         🔲
```

> See [ROADMAP.md](./ROADMAP.md) for the full phased breakdown with deliverables and success criteria.

---

## 🔧 Tech Stack

```
┌─────────────────────────────────────────────────────┐
│                    PROJECT KOBE                     │
├──────────────┬──────────────────────────────────────┤
│ Wake Word    │ OpenWakeWord (local, free)            │
│ STT          │ faster-whisper (RTX 3060, GPU)        │
│ Brain        │ OpenClaw + Claude Sonnet 4.6          │
│ TTS          │ ElevenLabs → OpenAI TTS fallback      │
│ HUD          │ Local web app → Electron              │
│ Gestures     │ MediaPipe Hands + Logitech C922       │
│ Printer      │ Bambu Lab P1S (local + cloud API)     │
│ Alerts       │ Discord webhooks                      │
│ CAD          │ FreeCAD (free)                        │
└──────────────┴──────────────────────────────────────┘
```

---

## 🖥️ Hardware

```
┌──────────────────────────────────────────────────┐
│  Lambert's Desk Setup                            │
├──────────────────────────────────────────────────┤
│  💻  Windows PC          RTX 3060 GPU            │
│  🖥️  Monitor 1           Primary display         │
│  🖥️  Monitor 2           KOBE HUD (always-on)    │
│  🎙️  USB Microphone      Voice input             │
│  🔊  Dedicated Speakers  TTS output              │
│  📷  Logitech C922       Gesture tracking        │
│  🖨️  Bambu Lab P1S       3D printer              │
│  ✨  65cm Holo Fan       Ambient display (Ph.7)  │
└──────────────────────────────────────────────────┘
```

---

## 💬 Voice Experience Design

KOBE responses are **concise by design**. No rambling. No filler.

| Scenario | KOBE Says |
|----------|----------|
| App launch | *"Opening VS Code."* |
| Print status | *"63% complete, about 42 minutes left."* |
| Confirmation | *"I can cancel the print. Confirm?"* |
| Task done | *"Done."* |

---

## 📁 Repository Structure

```
Project-KOBE/
├── 📂 docs/
│   ├── ARCHITECTURE.md              ← System design
│   ├── BOM.md                       ← Bill of materials (CAD prices)
│   ├── BUDGET.md                    ← Full budget breakdown
│   ├── Project KOBE - Detailed Spec.md
│   └── Project KOBE - Voice Assistant Plan.md
│
├── 📂 src/
│   ├── wake/          ← Wake word detection service
│   ├── stt/           ← Speech-to-text (faster-whisper)
│   ├── tts/           ← Text-to-speech (ElevenLabs)
│   ├── brain/         ← Conversation router + OpenClaw bridge
│   ├── hud/           ← HUD frontend + backend
│   ├── integrations/  ← Spotify, Steam, Bambu, Discord
│   ├── automation/    ← PC automation + app control
│   ├── gestures/      ← Gesture recognition
│   └── vision/        ← Screen vision service
│
├── 📂 config/         ← Configuration files
├── 📂 assets/         ← Icons, fonts, visuals
├── 📂 scripts/        ← Setup and utility scripts
├── 📂 tests/          ← Module tests
├── 📂 .github/        ← CI/CD workflows
│
├── ROADMAP.md
├── CONTRIBUTING.md
├── SECURITY.md
└── README.md
```

---

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [📋 Detailed Spec](./docs/Project%20KOBE%20-%20Detailed%20Spec.md) | Full 27-section planning spec and phased roadmap |
| [🎤 Voice Assistant Plan](./docs/Project%20KOBE%20-%20Voice%20Assistant%20Plan.md) | Voice pipeline options and quick-start plan |
| [🏗️ Architecture](./docs/ARCHITECTURE.md) | System architecture and module map |
| [🗺️ Roadmap](./ROADMAP.md) | Phased build roadmap with checkboxes |
| [💰 Budget](./docs/BUDGET.md) | Hardware + API cost breakdown in CAD |
| [🧾 Bill of Materials](./docs/BOM.md) | Full BOM with exact prices and purchase links |
| [🤝 Contributing](./CONTRIBUTING.md) | Branch strategy and commit guidelines |
| [🔒 Security](./SECURITY.md) | Security and secrets policy |

---

## 💰 Budget Summary

| Category | Cost (CAD) |
|----------|-----------|
| New hardware (all 7 phases) | ~$413 one-time |
| ElevenLabs TTS (monthly) | ~$15/mo |
| Everything else (STT, wake, gestures, AI) | **$0** — all local/free |
| **Year 1 total** | **~$593 CAD** |

> Full breakdown → [docs/BUDGET.md](./docs/BUDGET.md) · Full BOM → [docs/BOM.md](./docs/BOM.md)

---

## ⚠️ Project Status

> **Phase 1 + Phase 2 landed.** Voice pipeline (wake → STT → brain → TTS → actions + mute) plus a live HUD (FastAPI backend, WebSocket-driven JARVIS-style frontend, system telemetry) are all wired against a shared asyncio event bus. Requires `config/.env` with API keys before end-to-end use.

### Running

```bash
# 1. Install uv if you don't have it (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# 2. Sync deps (uses Python 3.11 via .python-version)
uv sync

# 3. Copy the env template and fill in keys
cp config/.env.example config/.env
# edit config/.env → ELEVENLABS_API_KEY, OPENCLAW_API_KEY, OPENCLAW_API_URL, ...

# 4. Smoke tests (no API keys / mic / speakers required)
uv run python scripts/smoke_phase1.py   # brain → tts → actions path
uv run python scripts/smoke_phase2.py   # HUD routes + WS protocol
uv run python scripts/smoke_phase3.py   # confirmation flow + executor allowlist
uv run python scripts/smoke_phase4.py   # vision capture + null backend + screen_inspect action

# 5. Run the live pipeline (start your terminal as Administrator
#    if you want the ctrl+alt+k global mute hotkey to work)
uv run kobe run

# 6. Open the HUD on your second monitor in kiosk mode
start chrome --kiosk http://127.0.0.1:8765
```

> **GPU note**: `faster-whisper` defaults to CUDA with `int8_float16`. On a 4 GB GPU, stay on `base.en` (default). Set `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8` to disable CUDA.

> **Wake word note**: "Hey KOBE" has no pretrained model yet. Default is `hey_jarvis` as a stand-in. Train a custom OpenWakeWord model and point `WAKE_MODELS` at the `.onnx` file when ready.

> **Mute note**: The `keyboard` module often needs admin on Windows to install its low-level hook. If `ctrl+alt+k` doesn't work, run your terminal as Administrator, or swap in a different hotkey backend later.

---

<p align="center">
  <i>Built by Lambert · Powered by OpenClaw + Claude · Inspired by JARVIS</i><br/>
  <i>🐾 Managed by KOBE</i>
</p>
