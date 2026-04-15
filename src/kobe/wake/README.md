# 🎙️ Wake Service

> **Phase 1** · Status: ✅ Built

Listens for wake words and fires `WakeDetected` onto the bus so the STT and TTS services can take over.

---

## What's built

- `service.py` — `run_wake_service(bus, settings, audio_source)` runs OpenWakeWord on the shared `audio.py` mic source, suppresses itself during `RecordingStarted / Stopped`, `SpeakStarted / Finished`, and `MuteToggled(True)`, and publishes `WakeDetected` on a hit.
- Default model: `hey_jarvis` as a stand-in until a custom "Hey KOBE" ONNX is trained — set `WAKE_MODELS` in `config/.env` to swap it in.
- Cold-start warm-up and per-model score thresholds are pulled from `config.py`.

## Responsibilities

- Always-on wake word detection
- Support "Hey KOBE" and "OK KOBE"
- Pause during speak / record / mute to prevent self-retrigger
- Pass activation signal to `stt_service` via `WakeDetected`

## Technology

| Component | Choice |
|-----------|--------|
| Wake word engine | [OpenWakeWord](https://github.com/dscripka/openWakeWord) |
| Current wake phrase | `hey_jarvis` (stand-in; custom "Hey KOBE" model planned) |
| Mute modes | Software mute (global hotkey) + physical button (Phase 6) |

## Inputs / Outputs

- **Input:** `audio.py` mic fan-out + `MuteToggled` / `SpeakStarted` / `RecordingStarted` events for suppression
- **Output:** `WakeDetected` on the bus → consumed by `stt_service`, `tts_service` (barge-in), `hud_backend`
