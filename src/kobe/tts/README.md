# 🔊 TTS Service

> **Phase 1** · Status: ✅ Built

Converts `ResponseReady` text into spoken audio, with ElevenLabs primary / OpenAI fallback and a real barge-in path.

---

## What's built

- `service.py` — `run_tts_service(bus, settings)` consumes `ResponseReady`, streams synthesis to the speakers, and publishes `SpeakStarted` / `SpeakFinished` bracketing each utterance.
- ElevenLabs primary (`ELEVENLABS_API_KEY` + voice id). Falls through to OpenAI TTS (`OPENAI_API_KEY`) on failure, then to a silent no-op if neither is configured.
- Barge-in: `InterruptRequested` (from mute) and `WakeDetected` during speak state both cancel the active playback cleanly; `SpeakFinished` is still emitted so the wake/stt suppression state machine resets.

## Responsibilities

- Convert response text to speech
- Stream audio to speakers
- Publish speaking-state events so `wake_service` / `stt_service` know when to suppress
- Support barge-in interruption

## Technology

| Component | Choice | Cost |
|-----------|--------|------|
| Primary TTS | [ElevenLabs](https://elevenlabs.io) — Creator plan | ~$15 CAD/mo |
| Backup TTS | OpenAI TTS | Pay-per-use |
| Local fallback | (planned, Phase 6) | Free |

## Voice design

KOBE's voice should be:
- Calm and clear
- Deep, neutral, confident
- Natural — not robotic
- Brief — voice responses are shorter than text responses

**Recommended voice:** ElevenLabs — "Adam" or equivalent

## Inputs / Outputs

- **Input:** `ResponseReady` text from `brain/router.py`; `InterruptRequested` from `mute/service.py`
- **Output:** Audio to default output device; `SpeakStarted` / `SpeakFinished` on the bus

## Response style in voice mode

```
✅ "Done."
✅ "Opening VS Code."
✅ "Print is 63% complete, about 42 minutes left."
✅ "I can cancel the print. Confirm?"

❌ "Sure! I'd be happy to help you open VS Code right now!"
```
