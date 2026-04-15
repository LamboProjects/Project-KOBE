# 🗺️ Project KOBE — Roadmap

> Phased build plan. Each phase has clear deliverables and a success criterion before moving to the next.

---

## Phase 1 — 🎤 Core Voice MVP  ✅

**Goal:** KOBE can hear, think, and speak reliably on the PC.

> *Success: KOBE responds quickly and consistently. Saying "Hey KOBE, open Spotify" actually works.*

- [x] Wake word detection (`Hey KOBE` / `OK KOBE`) — OpenWakeWord, `hey_jarvis` stand-in until a custom model is trained
- [x] Local STT with faster-whisper (GPU-accelerated, `base.en` int8_float16 default)
- [x] High-quality TTS output (ElevenLabs primary, OpenAI fallback)
- [x] Barge-in / interruption support (speaking-state-gated)
- [x] Software mute toggle (global hotkey, also issues InterruptRequested)
- [x] Physical mute button scaffold (TODO marker for Phase 6 MuteMe Mini)
- [x] Basic voice command routing (OpenClaw HTTP, echo stub when unconfigured)
- [x] App launching by voice (`open VS Code`, `open Spotify`, etc.)

**Landed in commit [`eb03903`](../../commit/eb03903).**

---

## Phase 2 — 🖥️ HUD MVP  ✅

**Goal:** Give KOBE persistent visual presence on the second monitor.

> *Success: KOBE feels like a live desktop system, not just a voice utility.*

- [x] Fullscreen always-on HUD (second monitor, kiosk-style) — FastAPI + WebSocket at `127.0.0.1:8765`
- [x] KOBE state indicator (muted / idle / listening / thinking / speaking) — derived server-side, CSS-animated client-side
- [x] Live voice transcript panel (last 8 transcripts, hydrated on reconnect)
- [x] Active response display panel
- [x] Basic system status widgets (clock, foreground app, CPU, memory)
- [x] Visual theme locked in — dark, cyan/magenta/amber accents, JetBrains Mono, scanline + vignette overlays

**Landed in commit [`9cb4888`](../../commit/9cb4888).**

---

## Phase 3 — 🖨️ Productivity & Printer Integration  ✅

**Goal:** Make KOBE materially useful in real daily workflows.

> *Success: KOBE is genuinely part of daily printing and desktop work.*

- [x] Bambu Lab P1S dashboard on HUD (live progress / stage / temps / connection)
- [x] Voice queries for print state (`bambu_status` action returns a TTS-ready summary)
- [x] Print completed / failed alerts via Discord webhook (dedup'd, color-coded)
- [x] Pause / resume / cancel print with spoken confirmation (destructive actions route through `ConfirmationRequested` → TTS prompt → STT yes/no)
- [x] App automation improvements — system volume via pycaw, window focus/minimize/maximize via pygetwindow, show-desktop via win+d
- [x] Spotify control (play, pause, next, previous, volume) with now-playing HUD panel
- [x] Steam game launch by voice (`steam://` URI via `steam_launch_game` + alias map)
- [x] Action executor split: generic (open_app/url/noop) stays central, integrations own their own action namespaces — no double-dispatch, no phantom failures

---

## Phase 4 — 👁️ Screen Vision & Context Awareness  ✅

**Goal:** Increase usefulness during active work.

> *Success: KOBE can interpret what's on screen in a practical, helpful way.*

- [x] Foundation: `mss` capture (foreground / full / region — region requires a valid box, never silently widens), pluggable `VisionBackend` protocol with `NullBackend` stub, async `vision_service` wired into the bus and the `screen_inspect` action namespace
- [x] **Real backends**: `OpenAIBackend` (gpt-4o-mini default, JPEG over data-URL) and `OpenClawBackend` (multipart POST to your VPS' `/v1/vision`). Both return `(ok, text)` so the HUD/ActionCompleted can distinguish a real answer from a fallback string
- [x] On-demand screen inspection (`what's on my screen?`) via `VisionRequested` event or `ActionRequested("screen_inspect", {...})` from the brain
- [x] Active app context detection — `kobe.vision.context.detect_context(window_title)` classifies into 14 known apps + `generic`; pure function, ordered substring rules
- [x] Per-app specialists — `kobe.vision.specialists.augment_question(question, context)` wraps the user's question with app-specific framing for VS Code, Bambu Studio, FreeCAD, Fusion 360, Blender, Obsidian, Chrome/Firefox, Excel, Slack/Discord, terminal, Explorer
- [x] HUD vision panel — last-scan summary + meta + question, `SCANNING…` shimmer with 45 s safety timer, `HudSnapshot` hydration on reconnect
- [x] Privacy: `image_path` is stripped from every WebSocket payload (cache + broadcast) so the HUD never receives a server-local file path

---

## Phase 5 — 👋 Gesture Control  ✅

**Goal:** Add a second natural interaction channel without sacrificing reliability.

> *Success: Gesture features work consistently and feel natural — not like a demo.*

- [x] Logitech C922 webcam integration — `cv2.VideoCapture(idx, CAP_DSHOW)` + 1-frame buffer to avoid stale frames
- [x] MediaPipe hand tracking — Tasks API `GestureRecognizer` in `LIVE_STREAM` mode (research-recommended over deprecated `solutions.hands`)
- [x] Swipe left / right — landmark-9 motion buffer + lookback dx threshold + consecutive-frame voting
- [x] Point — pretrained `Pointing_Up`
- [x] Confirm — pretrained `Thumb_Up` / `Open_Palm`
- [x] Dismiss — pretrained `Closed_Fist` / `Thumb_Down` + custom shake detector
- [x] HUD panel navigation by gesture — `swipe_left/right` cycles a `data-focused` outline across all visible panels; `select`/`confirm` flashes; `dismiss` clears
- [x] Reliability tuning: per-name cooldowns, static-vote debounce, no-hand resets static + motion state, held-pose can't re-fire across cooldown, shake suppresses spurious swipe, webcam-health flips on consecutive read failures, mute drains the queue
- [x] Privacy: no camera frames or hand landmarks are sent to the HUD — only the recognised semantic gesture name + confidence

**Setup:** `uv sync --extra gestures` (mediapipe is opt-in so non-gesture installs don't require a webcam-capable wheel).

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
