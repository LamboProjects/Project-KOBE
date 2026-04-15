# 🗣️ STT Service

> **Phase 1** · Status: ✅ Built

Captures audio after wake and transcribes it to text, gated by a simple energy VAD.

---

## What's built

- `service.py` — `run_stt_service(bus, settings, audio_source)` subscribes to `WakeDetected`, pulls pre-roll + live frames from the shared mic, runs faster-whisper in-process, and publishes `RecordingStarted`, `RecordingStopped`, and `TranscriptReady(text)`.
- Default model: `base.en` with `int8_float16` on CUDA — stays inside the 4 GB VRAM ceiling on the RTX 3050 Ti.
- RMS-energy VAD with trailing silence timeout handles end-of-speech; no cloud Whisper fallback is wired right now (kept free + private).

## Responsibilities

- Capture audio after wake word trigger (including 5 s pre-roll from `audio.py`)
- Transcribe speech to text locally on CUDA
- Publish `TranscriptReady` to the brain router
- Cooperate with `tts_service` / `wake_service` for barge-in

## Technology

| Component | Choice |
|-----------|--------|
| STT Engine | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| Compute | Local GPU — RTX 3050 Ti · 4 GB VRAM (`base.en`, `int8_float16`) |
| CPU fallback | Set `WHISPER_DEVICE=cpu` + `WHISPER_COMPUTE_TYPE=int8` in `config/.env` |

## Inputs / Outputs

- **Input:** `WakeDetected` event + mic frames from `audio.py`
- **Output:** `RecordingStarted / Stopped`, `TranscriptReady(text)` on the bus
