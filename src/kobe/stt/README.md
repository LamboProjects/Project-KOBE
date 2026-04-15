# 🗣️ STT Service

> **Phase 1** · Status: 🔲 Not started

Converts microphone audio to text after wake word activation.

---

## Responsibilities

- Capture audio after wake word trigger
- Transcribe speech to text (local, GPU-accelerated)
- Pass transcription to `conversation_router`
- Support barge-in / interruption of TTS playback

## Technology

| Component | Choice |
|-----------|--------|
| STT Engine | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| Compute | Local GPU — RTX 3060 |
| Fallback | OpenAI Whisper API |

## Why faster-whisper?

- Free — no per-minute API cost
- Private — audio never leaves the machine
- Fast — GPU-accelerated on RTX 3060
- Quality — comparable to cloud Whisper

## Inputs / Outputs

- **Input:** Wake trigger + microphone audio stream
- **Output:** Transcribed text → `conversation_router`

## Notes

- Should handle end-of-speech detection cleanly
- Barge-in support requires coordinating with `tts_service` to know when KOBE is speaking
