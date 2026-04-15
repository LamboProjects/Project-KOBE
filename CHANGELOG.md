# Changelog

All notable changes by phase. Each entry links to the commit that landed it.

The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) (Added / Changed / Fixed) but is grouped per phase rather than per semver bump — KOBE is a single-user assistant, no public versioning yet.

---

## Post-Phase-7 — 🔬 Autoresearch-style gesture classifier tuning

Ran Karpathy's autoresearch loop (edit → commit → eval → keep/revert) against `src/kobe/gestures/classifier.py` on a 44-case synthetic benchmark (34 train + 10 heldout), then 12 rounds of harsh `codex review --base main`. Every bug Codex caught has a named regression canary in `scratch/autoresearch_kobe/synth.py`.

### Changed
- **`src/kobe/gestures/classifier.py`** — adds `_static_hold_lock` + unified `_static_release_streak` mechanism. After a static gesture fires, records the KOBE semantic name (`confirm`/`dismiss`/`point`). Subsequent ticks that vote to the same winner are suppressed until an explicit release:
  - `has_hand=False` (hand left the frame), OR
  - `gesture_static_required` consecutive frames that are *not* held-consistent (unmapped, low-score, **or** a different KOBE mapping — unified so a single `Closed_Fist` misclassification during a `Thumb_Up` hold doesn't defeat the lock).
  When the release-streak crosses threshold, the vote deque is also drained — otherwise sustained cross-semantic misclassification would clear the lock *and* immediately fire the opposite semantic from those same stale votes.

### Fixed
- **Held-pose duplicate fire across cooldown** — pre-existing bug: a user holding `Thumb_Up` for longer than `gesture_cooldown_ms` (1.2 s default, 36 frames @ 30 fps) would get a second `confirm` event around frame 40 as the vote deque refilled. The hold-lock blocks this. Canary: `hard_no_refire_during_hold`.
- **MediaPipe flicker during hold (same-semantic)** — one unmapped/`Victory` frame every 10 during a long hold would have cleared a naive raw-label lock; the KOBE-semantic lock plus release-streak gate ignores it. Canaries: `hard_flicker_during_hold`, `hard_long_same_semantic_flicker`.
- **Cross-semantic misclassification** — a single `Closed_Fist` frame during a `Thumb_Up` hold no longer clears the lock; a sustained 5-frame misclassification clears it *and* drains the vote buffer, so no spurious `dismiss` fires from the stale votes. Canaries: `hard_cross_mapping_flicker`, `hard_cross_mapping_sustained`.
- **In-frame release** — user fires confirm, relaxes to a neutral pose without leaving the camera view, then forms `Thumb_Up` again → second confirm fires. The release-streak accumulates on unmapped frames and clears the lock once it crosses `gesture_static_required`. Canary: `hard_relax_inframe_then_refire`.
- **Direct pose switch** — `Thumb_Up` hold directly to `Closed_Fist` with no no-hand gap still fires `dismiss` (with a design-accepted ~4-frame extra latency, preferable to cross-semantic false fires on misclassification). Canary: `hard_direct_pose_switch`.

### Metrics (44-case synthetic benchmark, train + heldout union)

| Metric    | Baseline (main) | After          | Δ        |
|-----------|-----------------|----------------|----------|
| F1        | 0.9552          | **0.9756**     | +0.0204  |
| Precision | 0.9697          | **1.0000**     | +0.0303  |
| Recall    | 0.9412          | 0.9524         | +0.0112  |
| Latency   | 5.50            | 5.30           | −0.20    |
| Score     | 0.9277          | **0.9491**     | +0.0214  |

Zero false positives. The 2 remaining `fn` cases are intentional dataset contradictions (same MediaPipe input, opposite expected outcomes) that no algorithm can distinguish.

### Sweeps tried and reverted
- `gesture_min_score` 0.6 → 0.5: +0.0015 synthetic score but admits 0.50–0.59 MediaPipe noise in production (Codex R4 P2).
- `gesture_static_window` 6 → 8: +0.0003 synthetic score but lowered the effective debounce ratio from 5/6 (83 %) to 5/8 (63 %) — `hard_fragmented_votes` canary pins this tradeoff (Codex R9 P1).
- 1-frame swipe-streak grace: no case in the synthetic dataset exercised it.

### Added
- `scratch/autoresearch_kobe/` — reusable tuning infrastructure:
  - `program.md` — protocol for the loop.
  - `synth.py` — 44 deterministic labeled streams, split 34 train / 10 heldout, with 7 regression canaries for Codex findings.
  - `harness.py` — scores classifier via F1 + latency, `_pristine_settings()` factory bypasses `env_file` and `GESTURE_*` env vars so benchmarks are machine-independent.
  - `run_experiment.py` — appends a row to `results.tsv` per commit; crashes logged as `crash` status (not silently dropped).
  - `iterate.py` — in-process param sweeper, validates `--param` names against `Settings.model_fields` to reject typos.
  - `FINDINGS.md` — final writeup, kept/reverted experiments, per-round Codex correspondence.

---

## Phase 7 — 🌀 Holographic Fan Integration · [`cd14b0f`](../../commit/cd14b0f) + audit [`ea46265`](../../commit/ea46265)

Pluggable content pipeline for 65 cm WiFi holographic fans. Because no vendor in this class publishes an API, KOBE ships the content-generation + backend-abstraction half; the user drops in their own device driver after pcaping the vendor app.

### Added
- `src/kobe/fan/driver.py` — `FanBackend` Protocol + `BackendHealth` + three concrete backends: `NullBackend` (log stub), `FileOutputBackend` (atomic `os.replace` swap of `current.mp4` with rolling retention), `HttpPushBackend` (scaffold with full protocol docstring — POST `/upload` + POST `/play` + Bearer auth + TODO(pcap) markers).
- `src/kobe/fan/content.py` — `render_rotating_logo`, `render_progress_ring`, `render_spotify_waveform`, `render_gesture_flash`, `render_stl_rotation`. 512×512, 30 fps, H.264 yuv420p on pure black. SHA-1 hash dedup on inputs so identical scenes don't re-render.
- `src/kobe/fan/service.py` — priority stack: gesture flash > printer progress > Spotify waveform > idle logo/STL. Three fan-in subscribers with drop-oldest work queue. Renders off the loop via `functools.partial` + `asyncio.to_thread`. Honors `hologram_clip_cooldown_s` (gesture flashes preempt). Only advances `last_pushed_hash` + emits `FanClipPushed` on backend success. Probes `imageio` at startup and disables cleanly when the `hologram` extra isn't installed. Seeds the idle queue at startup so the fan isn't blank for the first logo-refresh interval.
- HUD compact FAN pill in the brand panel with backend tag, connection dot, current clip name, and a 500 ms flash on every new push.
- `FanClipPushed`, `FanBackendStatus` events. HUD backend `_EVENT_TYPES` + snapshot cache extended; `path` scrubbed from both cache and broadcast.
- 11 new `hologram_*` Settings fields with research-recommended defaults. New optional extra `hologram` = `imageio>=2.34` + `imageio-ffmpeg>=0.5` + `trimesh>=4.4` + `pyglet>=2.0` (Windows).
- `scripts/smoke_phase7.py` — factory dispatch, content hash internals, and end-to-end service run with `NullBackend` asserting a `GestureDetected` produces a `FanClipPushed(path="")`.

### Fixed (during the Codex review loop)
- Service called content generators positionally but they're keyword-only — would have TypeError'd every render. Wrapped in `functools.partial`.
- `BackendHealth.name` vs service `getattr("backend", ...)` contract drift — service now reads `.name`.
- Service advanced `last_pushed_hash` + published `FanClipPushed` even on backend failure — now success-gated.
- `content.render_stl_rotation` caught `BaseException`, swallowing `CancelledError` — narrowed to `Exception`.
- `hologram_enabled` defaulted on, but a base install without the extra would spam render failures — now probes `imageio` up-front and disables cleanly.
- Idle timer waited a full `hologram_logo_refresh_s` (60 s default) before the first push — now seeds an immediate idle tick so the fan shows content within a second.
- HUD unknown-backend name could inflate the pill — now capped at 6 chars.

### Cross-phase integration audit fixes (committed alongside Phase 7)
- **Wake service crash propagation** — `_load_model` raising `RuntimeError` (e.g. missing openwakeword wheel) would bubble into the `asyncio.TaskGroup` and cancel every other service. Wake now degrades cleanly and logs a hint; the rest of the pipeline keeps running.
- **`mute/service.py` hotkey cleanup** — some `keyboard` versions return `None` from `add_hotkey` even on success, which would leak the low-level OS hook across dev restarts. Fall back to string-based `remove_hotkey(mute_hotkey)` when the handle is missing.
- **`brain/router.py` shutdown log asymmetry** — stub mode now also logs `brain_service_stopped` for symmetric service lifecycle traces.
- **Discord digest sub-minute clamp** — if the user set a fractional `discord_digest_interval_hours` (< 0.0167 → under 60 s), the clamp to 60 s was silent. Logs `discord_digest_interval_floored` on startup.
- **`vad_aggressiveness` config docstring** — old "webrtcvad" reference corrected to explain we use an RMS-energy VAD (webrtcvad pulled out in Phase 1 to avoid MSVC dep on Windows).

---

## Phase 6 — ✨ Premium Polish · [`7c4f9be`](../../commit/7c4f9be)

Personas, smart-home integration, physical MuteMe button, multi-profile scaffold, richer Discord alerts, smoother HUD.

### Added
- `src/kobe/brain/personas.py` — 5 named presets (`default`, `concise`, `warm`, `terse`, `excited`); any other string ships verbatim as a custom prompt. `persona_prompt` field added to OpenClaw POST body.
- `src/kobe/integrations/home_assistant.py` — REST integration with actions `home_light_on/off/toggle`, `home_switch_on/off`, `home_scene_activate`, `home_state`, plus a generic `home_*` pass-through. Unconfigured-state stub returns a clear `ActionCompleted(ok=False, …)` instead of a silent hang.
- `src/kobe/mute/muteme.py` — MuteMe Mini over cython-hidapi. Enumerates all 4 known VID/PID pairs, prefers input-capable interface (usage_page 0x01/0x0C/vendor), blocking-read producer thread, LED feedback, bus-mirror with idempotent echo-dedupe. Best-effort LED writes can't crash the TaskGroup; `stop_flag` set on read failure so an unplug doesn't emit a phantom toggle.
- `src/kobe/profiles/manager.py` — `Profile` dataclass + `run_profile_service`. Tiny inline dotenv parser (no `python-dotenv` dep). Actions: `profile_switch`, `profile_list`, `profile_show`. Emits `ProfileChanged` on startup (with a 50 ms yield so the HUD has time to subscribe) and on every switch. Repo-relative path resolution so profile files are found regardless of CWD.
- `ProfileChanged` event. HUD brand panel now shows the active profile as a `#profile-tag` chip with live updates + snapshot hydration.
- HUD polish pass: 250 ms fade/scale handoff on state-orb label+sub with timer de-dup, concentric thinking-arc spinner, `prefers-reduced-motion` media query, gentler connection-dot pulse, transcript fade-in, response typing cursor.
- `scripts/smoke_phase6.py` — persona registry + custom-prompt passthrough, profile startup + `profile_show`, HA unconfigured degradation, MuteMe no-device degradation.

### Changed
- TTS (`src/kobe/tts/service.py`) — threads `stability` / `similarity_boost` / `style` / `use_speaker_boost` into `text_to_speech.convert(voice_settings=...)`, with graceful `TypeError` fallback for older ElevenLabs SDKs.
- Brain (`src/kobe/brain/router.py`) — adds optional `persona_prompt` field to the OpenClaw chat request body. Documented in `docs/OPENCLAW.md`.
- Discord (`src/kobe/integrations/discord.py`) — richer `PrinterAlert` embed with live Progress / Remaining / Nozzle / Bed / Stage fields and a 20-char ASCII progress bar; inline-drain of `PrinterStatus` in the alert loop closes the cross-task ordering race so alerts never carry the previous job's snapshot; optional periodic digest; 429 retry-after honoured (header treated as seconds regardless of magnitude; body keeps the `>120 → ms` legacy heuristic; both clamped to 300 s). Cache reset on service start.
- `__main__.py` — startup config dump now excludes `bambu_access_code`, `spotify_client_secret`, `discord_webhook_url`, and `homeassistant_token` alongside the existing key fields.

### Fixed (during the Codex review loop)
- Profile switch double-speak (brain's model text + manager's own TTS) — the manager no longer publishes `ResponseReady`; the brain's reply is the single source of truth.
- Persona fallback regressions from the custom-prompt change — any non-preset string is now passed through verbatim (logged at INFO), including short ones like `snarky`; only empty/None silently falls back to `default`.
- MuteMe phantom mute on unplug — reader thread now sets `stop_flag` before waking the async side, so the wake-up can no longer be mistaken for a button press.
- Discord stale-snapshot enrichment — alert and status are now consumed in the same task with inline drain.
- HA bearer token appearing in startup log — excluded from `model_dump`.

### Follow-ups noted
- Wire profile overrides back into live Settings (e.g. swap wake model / voice / persona on `profile_switch` without a restart).
- Subscribe to HA's `/api/websocket` for live state push into the HUD.
- Per-alert role-mention map in Discord settings (`@printer-crit` on `failed`).

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
