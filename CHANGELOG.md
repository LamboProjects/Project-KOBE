# Changelog

All notable changes by phase. Each entry links to the commit that landed it.

The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (Added / Changed / Fixed) but is grouped per phase rather than per semver bump — KOBE is a single-user assistant, no public versioning yet.

---

## Phase 5 — 👋 Gesture Control · [`16fc7dd`](../../commit/16fc7dd)

Real-time webcam gesture recognition wired to HUD navigation.

### Added
- `src/kobe/gestures/camera.py` — `cv2.VideoCapture(idx, CAP_DSHOW)` + MediaPipe Tasks `GestureRecognizer` in `LIVE_STREAM` mode on a dedicated producer thread; bridges back to the asyncio loop via `loop.call_soon_threadsafe`. Auto-downloads the ~8 MB `gesture_recognizer.task` model to `~/.cache/kobe/` on first run. Webcam health flips `connected=False` after sustained `cap.read()` failures.
- `src/kobe/gestures/classifier.py` — pure deque-based static + swipe + shake recognizers. Per-name cooldowns; static-vote debounce (5-of-6 frames at score ≥ 0.6); landmark-9 motion buffer for swipes; `_shake_qualifies()` suppresses spurious swipes when shake is cooldown-blocked. No-hand frame resets ALL state before fire-check, so a tracking gap forces release-and-reform. Held pose can't re-fire across cooldown.
- `src/kobe/gestures/service.py` — async service. Mute-aware (drops queued frames AND resets the classifier on every transition). Maps gestures to `hud_navigate_prev/next`, `hud_select`, `hud_confirm`, `hud_dismiss`. Telemetry every 2 s.
- HUD vision panel — gesture badge with glyph + label + accent flash; webcam ONLINE/OFFLINE pill with FPS readout; `data-focused` outline cycles across panels (resolved by class so previously-class-only panels participate).
- `GestureDetected`, `WebcamStatus` event types. 19 new `gesture_*` / `camera_*` Settings fields.
- `scripts/smoke_phase5.py` — mock-driven (no real webcam): exercises pretrained → KOBE static-gesture mapping, cooldowns, swipe motion, no-hand resets, and the gesture→action map.

### Changed
- `mediapipe` moved to `[project.optional-dependencies].gestures`. Install via `uv sync --extra gestures`. Don't add `opencv-python` separately — `mediapipe` already ships `opencv-contrib-python` (provides `cv2`).

### Fixed (during the 8-round Codex review loop)
- Camera shutdown race — late MP callbacks no longer touch a closed recognizer.
- `ensure_model` cancellation cleanup — `.part` tempfile removed on `BaseException`.
- HUD nav pointed at non-existent panel ids — switched to class selectors so the cycle has no dead stops.

---

## Phase 4 — 👁️ Screen Vision · [`d0acb51`](../../commit/d0acb51) (foundation), [`0d65b73`](../../commit/0d65b73) (full)

On-demand screen inspection with pluggable vision backends and per-app prompt routing.

### Added
- `src/kobe/vision/capture.py` — `mss`-based screenshot for foreground / full / region. Region requires a valid box (no silent widening to all monitors).
- `src/kobe/vision/backends.py` — `VisionBackend` Protocol returning `(ok, text)`. Real backends: `OpenAIBackend` (gpt-4o-mini default, JPEG over `image_url` data URL) and `OpenClawBackend` (multipart POST to `/v1/vision`). Shared `encode_jpeg` downsamples + JPEG-encodes.
- `src/kobe/vision/context.py` — pure `detect_context(window_title) → WindowContext`. 14 known apps (vscode, bambu_studio, freecad, fusion360, blender, obsidian, chrome, firefox, terminal, excel, slack, discord, explorer + `generic` fallback).
- `src/kobe/vision/specialists.py` — `augment_question(q, ctx)` wraps user questions with app-specific framing. Skipped for the `null` backend so its echo response stays clean.
- `src/kobe/vision/service.py` — async service. Triggers from `VisionRequested` event or `ActionRequested("screen_inspect", ...)`. Always emits `VisionResult` + `ResponseReady`.
- HUD "VISION · LAST SCAN" panel with status pill, summary text, meta line, optional `Q:` line, and `SCANNING…` shimmer with a 45 s safety timer.
- `VisionRequested`, `VisionResult` event types. Vision settings (backend choice, JPEG quality, max edge, OpenAI model, OpenClaw vision endpoint).
- `scripts/smoke_phase4.py` — exercises the full capture → context → backend → result path with the null backend.

### Fixed (Codex)
- Backend transport failures were marked as `ok=True`; protocol now returns `(ok, text)`.
- `image_path` was scrubbed only from cache, leaked to live broadcast — now stripped from both.
- Null backend received augmented framing — service skips augmentation when backend is `null`.

---

## Phase 3 — 🖨️ Productivity & Printer Integration · [`7090417`](../../commit/7090417)

Printer, media, automation, and a confirmation flow for destructive actions.

### Added
- `src/kobe/integrations/bambu.py` — Bambu Lab P1S over LAN MQTT (paho-mqtt v2, insecure TLS). Maps `gcode_state` → stage, merges incremental diffs, publishes `PrinterStatus` + first-entry `PrinterAlert`. Handles `bambu_pause/resume/cancel_print` + `bambu_status`. Thread-safe seq counter; offline snapshot on disconnect so the HUD doesn't keep showing stale "online" data.
- `src/kobe/integrations/spotify.py` — spotipy client with `SpotifyOAuth` cache. Action handlers for play/pause/next/previous/volume; poller publishes `NowPlayingChanged` on every tick while playing so the HUD progress bar stays fresh.
- `src/kobe/integrations/steam.py` — `steam://` URI launcher with a name → app_id alias map.
- `src/kobe/integrations/discord.py` — webhook poster on `PrinterAlert` with emoji/color map and 3 s dedupe.
- `src/kobe/automation/windows_ctrl.py` — pycaw master volume (get/set/up/down/mute), pygetwindow focus/min-all/min-active/max-active, win+d for `show_desktop`. pycaw lazy-imports so COM-unavailable machines degrade gracefully.
- `src/kobe/actions/confirmation.py` — listens for `ConfirmationRequested`, speaks the prompt, waits for next `TranscriptReady`, classifies yes/no ("no wins ties"), publishes `ConfirmationResult` + (on yes) a regular `ActionRequested`.
- HUD additions — Printer panel, Now-Playing panel, Confirmation banner with amber → green/red flash.
- `PrinterStatus`, `PrinterAlert`, `NowPlayingChanged`, `ConfirmationRequested`, `ConfirmationResult` event types.
- `scripts/smoke_phase3.py` — covers executor allowlist (no phantom failures), confirmation flow end-to-end, and back-to-back confirmations.

### Changed
- Brain (`src/kobe/brain/router.py`) detects destructive actions via an explicit allowlist (`bambu_cancel_print`, `bambu_pause_print`) or a `requires_confirmation` flag in the OpenClaw response and publishes `ConfirmationRequested` instead of `ActionRequested`.
- Action executor (`src/kobe/actions/executor.py`) restricted to its owned actions (open_app/open_url/noop). Other actions are silently skipped — integrations publish their own `ActionCompleted`. Stops the phantom "unknown action" failures the review caught.

---

## Phase 2 — 🖥️ HUD MVP · [`9cb4888`](../../commit/9cb4888)

Always-on second-monitor dashboard reachable at `http://127.0.0.1:8765`.

### Added
- `src/kobe/hud/backend.py` — FastAPI app: `GET /` (index.html), `/static/*` mount, `/health`, `/ws`. Derives coarse HUD state (idle/listening/thinking/speaking/muted) from existing bus events. Single writer task drains an internal outbound queue and fans out to every client in parallel, serialized per client via `asyncio.Lock`.
- Bounded in-memory cache of last 8 transcripts, last response, and last `SystemStatus` so reconnecting clients get a hydrated `HudSnapshot`.
- `src/kobe/hud/static/{index.html,style.css,app.js}` — dark/cyan JARVIS-style dashboard: state orb, transcript log, response panel, clock, system widget. CSS-only state animations; `textContent`-only rendering (no XSS); auto-reconnect with backoff + de-dup.
- `src/kobe/system/status.py` — periodic poll via `psutil` + `pygetwindow`. Primed `cpu_percent` so the first emitted sample isn't 0.0.
- `SystemStatus` event type.
- `scripts/smoke_phase2.py` — verifies all HTTP routes return 200, the WS snapshot is typed `HudSnapshot`, and synthetic events round-trip to connected clients.

---

## Phase 1 — 🎤 Core Voice MVP · [`eb03903`](../../commit/eb03903)

Wake → STT → Brain → TTS → Actions, plus mute, all on a shared asyncio event bus.

### Added
- Shared infra: `src/kobe/{events,bus,config,audio,logging,__main__}.py`. Asyncio pub/sub with drop-oldest overflow; pydantic-settings with layered env-file resolution; single-owner mic source with thread-safe fan-out and 5 s pre-roll ring buffer; typer CLI entry point.
- `src/kobe/wake/service.py` — OpenWakeWord (onnx → tflite fallback). `hey_jarvis` stand-in until a custom "Hey KOBE" model is trained.
- `src/kobe/stt/service.py` — faster-whisper on CUDA (cpu/int8 fallback). Energy-based VAD to avoid `webrtcvad`'s MSVC build dep on Windows.
- `src/kobe/tts/service.py` — ElevenLabs primary (pcm_16000), OpenAI wav fallback. Barge-in gated on active-speaking state so stray `WakeDetected` events don't poison the next utterance.
- `src/kobe/brain/router.py` — HTTP POST to OpenClaw `/v1/chat` with echo stub when unconfigured.
- `src/kobe/actions/executor.py` — `open_app` / `open_url` / `noop`. Windows-safe quoting via `os.startfile` + explicit `cmd /c start` fallback.
- `src/kobe/mute/service.py` — global keyboard hotkey (degrades gracefully without admin); also publishes `InterruptRequested` on mute-true to stop ongoing TTS.
- `scripts/smoke_phase1.py` — exercises brain (stub) → tts → actions without needing mic / speakers / API keys.

---

## Pre-Phase 1 — Planning · [`d9a4a82`](../../commit/d9a4a82) and earlier

Repo scaffolding, README, ROADMAP, BOM, BUDGET, OPENCLAW integration doc, module placeholder folders.

---

*Cross-phase integration audit: [`c62fa03`](../../commit/c62fa03) (brain confirmation guard against double-processing the yes/no answer).*
