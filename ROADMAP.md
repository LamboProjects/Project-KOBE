# 🗺️ Project KOBE — Roadmap

> Phased build plan. Each phase has clear deliverables and a success criterion before moving to the next.

---

## Phase 1 — 🎤 Core Voice MVP

**Goal:** KOBE can hear, think, and speak reliably on the PC.

> *Success: KOBE responds quickly and consistently. Saying "Hey KOBE, open Spotify" actually works.*

- [ ] Wake word detection (`Hey KOBE` / `OK KOBE`)
- [ ] Local STT with faster-whisper (GPU-accelerated on RTX 3060)
- [ ] High-quality TTS output (ElevenLabs)
- [ ] Barge-in / interruption support
- [ ] Software mute toggle
- [ ] Physical mute button scaffold
- [ ] Basic voice command routing
- [ ] App launching by voice (`open VS Code`, `open Spotify`)

---

## Phase 2 — 🖥️ HUD MVP

**Goal:** Give KOBE persistent visual presence on the second monitor.

> *Success: KOBE feels like a live desktop system, not just a voice utility.*

- [ ] Fullscreen always-on HUD (second monitor, kiosk-style)
- [ ] KOBE state indicator (muted / idle / listening / thinking / speaking)
- [ ] Live voice transcript panel
- [ ] Active response display panel
- [ ] Basic system status widgets (time, date, app state)
- [ ] Visual theme locked in — dark, cyan/blue, futuristic

---

## Phase 3 — 🖨️ Productivity & Printer Integration

**Goal:** Make KOBE materially useful in real daily workflows.

> *Success: KOBE is genuinely part of daily printing and desktop work.*

- [ ] Bambu Lab P1S dashboard on HUD
- [ ] Voice queries for print state (`how's my print doing?`)
- [ ] Print completed / failed alerts via voice + Discord
- [ ] Pause / resume / cancel print with spoken confirmation
- [ ] App automation improvements (window management, volume, etc.)
- [ ] Spotify control (play, pause, next, volume, playlists)
- [ ] Steam game launch by voice
- [ ] Better desktop action support

---

## Phase 4 — 👁️ Screen Vision & Context Awareness

**Goal:** Increase usefulness during active work.

> *Success: KOBE can interpret what's on screen in a practical, helpful way.*

- [ ] On-demand screen inspection (`what's on my screen?`)
- [ ] Active app context detection
- [ ] Coding help in VS Code context
- [ ] Print settings review in Bambu Studio
- [ ] CAD troubleshooting assistance

---

## Phase 5 — 👋 Gesture Control

**Goal:** Add a second natural interaction channel without sacrificing reliability.

> *Success: Gesture features work consistently and feel natural — not like a demo.*

- [ ] Logitech C922 webcam integration
- [ ] MediaPipe hand tracking setup
- [ ] Swipe left / right gesture
- [ ] Point / select gesture
- [ ] Confirm / dismiss gesture
- [ ] HUD panel navigation by gesture
- [ ] Gesture reliability tuning

---

## Phase 6 — ✨ Premium Polish

**Goal:** Make KOBE feel cohesive, intentional, and impressive.

> *Success: KOBE feels polished and professional, not experimental.*

- [ ] ElevenLabs voice tuning and persona refinement
- [ ] Smoother HUD animations and state transitions
- [ ] Improved command handoff and confirmation flows
- [ ] Better Discord integration (richer alerts)
- [ ] Smart home hooks — smart plug → lights
- [ ] Physical mute button (MuteMe Mini)
- [ ] Multi-profile architecture prep (future: Jasmine)

---

## Phase 7 — 🌀 Holographic Fan Integration

**Goal:** Add spectacle and ambient visual presence as an enhancement layer.

> *Success: The fan enhances the system without becoming a dependency or distraction.*

- [ ] 65cm WiFi holographic fan setup and media pipeline
- [ ] KOBE logo rotation animation
- [ ] Music-reactive visuals (Spotify sync)
- [ ] Printer status visualization
- [ ] Gesture-linked fan effects
- [ ] 3D model display support

---

## Build Order (Within Phases)

```
1. Voice pipeline (wake → STT → route → TTS)
2. Wake word tuning
3. TTS quality + interruption
4. Basic command execution
5. HUD foundation
6. Printer integration
7. Discord alerts
8. Screen vision
9. Gesture control
10. Premium polish
11. Holographic fan
12. Smart home expansion
```

---

*See [docs/BOM.md](./docs/BOM.md) for hardware requirements per phase.*
