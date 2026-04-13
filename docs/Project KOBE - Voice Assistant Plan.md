# Project KOBE — Voice AI Assistant
**Created:** 2026-04-13  
**Owner:** Lambert  
**Status:** Planning

---

## Vision

Build a KOBE-style voice AI assistant — real-time voice in, voice out, always-on, feels alive. Not a wake-word button presser. An actual conversational presence that knows you, remembers context, and responds in a natural voice. Optional: interactive projector display with gesture control.

---

## Core Pillars

| Pillar | Description |
|--------|-------------|
| 🎤 Voice In | Mic → Speech-to-Text (STT) |
| 🧠 Intelligence | Claude (via OpenClaw/Kobe) |
| 🔊 Voice Out | Text-to-Speech (TTS) with a good voice |
| 💾 Memory | Persistent context across sessions |
| 🖥️ Interface | Always-on, low-latency, feels real |
| 📽️ Display | (Phase 4) Interactive projector HUD |

---

## Architecture Options

### Option A — Discord Voice Plugin (Easiest Start)
- Use **discord-voice** ClawHub skill on OpenClaw
- Pros: Already built, STT/TTS wired up, works today
- Cons: Requires Discord open, bot token, relies on Discord infra
- Voice providers: OpenAI (TTS nova voice), local Whisper (STT)
- **Best for:** Quick proof-of-concept this week

### Option B — Local Always-On App (Full KOBE)
- Python/Node app running on your PC or VPS
- Mic → Whisper (local STT) → OpenClaw API → ElevenLabs/OpenAI TTS → Speaker
- Wake word detection (OpenWakeWord / Porcupine)
- Pros: No Discord dependency, fully custom, can run on startup
- Cons: More setup, needs mic access on local machine
- **Best for:** The real long-term KOBE experience

### Option C — Hybrid (Recommended Path)
1. **Phase 1:** Start with Discord voice (fast, working today)
2. **Phase 2:** Build local Python pipeline for always-on
3. **Phase 3:** Add personality, memory, home automation hooks
4. **Phase 4:** Interactive projector display

---

## Tech Stack (Recommended)

### STT (Speech-to-Text)
- **Local:** `faster-whisper` (runs on CPU/GPU, free, private)
- **Cloud:** OpenAI Whisper API ($0.006/min — very cheap)

### TTS (Text-to-Speech)
- **OpenAI TTS** — "onyx" or "nova" voice, very natural, fast
- **ElevenLabs** — most natural/human, free tier available
- **Local:** Kokoro (built into discord-voice plugin, no API cost)

### Wake Word
- **OpenWakeWord** — open source, runs local, no cloud
- Custom wake word: "Hey KOBE"

### Brain
- OpenClaw + Kobe (Claude Sonnet 4.6 default)
- Already has memory, tools, Google Drive, calendar, etc.

### Interface
- Phase 1: Discord
- Phase 2: Python script running as a system service on your PC
- Phase 3: Optional web UI
- Phase 4: Projector HUD + gesture control

---

## Personality / Voice Direction

KOBE traits:
- Calm, warm, confident — like a golden retriever that also knows everything
- Responses are punchy — no filler words when speaking
- Acknowledges tasks with brevity: "Done.", "On it.", "Found it."
- Occasional dry wit
- Uses Lambert's name naturally but not every sentence

TTS Voice recommendation: **ElevenLabs "Adam"** or **OpenAI "onyx"** — deep, clear, neutral

---

## Phase 1 Action Plan (This Week)
*Goal: Voice conversation via Discord*

- [ ] Install `discord-voice` plugin on OpenClaw
- [ ] Create Discord bot (Discord Developer Portal)
- [ ] Configure: STT = local-whisper, TTS = openai/onyx, barge-in = on
- [ ] Test voice conversation in Discord voice channel
- [ ] Tune response style (short, punchy, KOBE-like)

## Phase 2 Action Plan (Next 2–4 Weeks)
*Goal: Always-on local assistant*

- [ ] Build local Python voice pipeline (mic → whisper → API → TTS)
- [ ] Add OpenWakeWord ("Hey KOBE")
- [ ] Run as a background service on Lambert's PC
- [ ] Connect to OpenClaw API for intelligence
- [ ] Add PC automation hooks (volume, apps, etc.)

## Phase 3 (Home Base)
*Goal: Deep integration*

- [ ] Home Assistant integration for smart home control
- [ ] Calendar / email voice briefings ("Good morning Lambert...")
- [ ] Custom ElevenLabs voice
- [ ] ESP32 status LED (listening / thinking / speaking indicators)

## Phase 4 (Interactive Projector)
*Goal: Holographic HUD vibes*

- [ ] Projector + Raspberry Pi / mini PC driving display
- [ ] KOBE web UI (React HUD): clock, weather, voice transcript, calendar, tool results
- [ ] Gesture input via webcam + MediaPipe (free, open source)
  - Hand tracking maps gestures to commands
  - Swipe to browse, point to select
- [ ] OR: Infrared touch frame (~$100–300) for finger touch on projected surface
- [ ] OR: Leap Motion / Ultraleap for mid-air hand tracking (~$80–150)
- [ ] Gesture commands trigger OpenClaw → KOBE responds via voice + updates display

### Projector Hardware Sketch
```
Projector → Wall/Desk surface
     ↑
Raspberry Pi / Mini PC
     ↑
Webcam (gesture tracking via MediaPipe)
     ↑
OpenClaw (brain) ← → Voice pipeline
```

---

## Notes

- OpenClaw already handles memory, tools, Drive, Calendar — KOBE brain is mostly done
- Biggest lift is the local audio pipeline (Phase 2)
- Discord route (Phase 1) can be done in an afternoon
- No paid APIs required for MVP: local Whisper + Kokoro TTS = $0/month
- Gesture recognition with MediaPipe + ~$30 webcam is genuinely impressive
