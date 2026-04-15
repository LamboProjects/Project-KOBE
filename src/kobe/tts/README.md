# 🔊 TTS Service

> **Phase 1** · Status: 🔲 Not started

Converts KOBE's text responses to natural spoken audio.

---

## Responsibilities

- Convert response text to speech
- Stream audio to speakers
- Support barge-in interruption (stop speaking mid-response)
- Notify `wake_service` when speaking (prevent re-trigger)

## Technology

| Component | Choice | Cost |
|-----------|--------|------|
| Primary TTS | [ElevenLabs](https://elevenlabs.io) — Creator plan | ~$15 CAD/mo |
| Backup TTS | OpenAI TTS | Pay-per-use |
| Local fallback | Kokoro (zero cost) | Free |

## Voice Design

KOBE's voice should be:
- Calm and clear
- Deep, neutral, confident
- Natural — not robotic
- Brief — voice responses are shorter than text responses

**Recommended voice:** ElevenLabs — "Adam" or equivalent

## Inputs / Outputs

- **Input:** Response text from `conversation_router`
- **Output:** Audio stream → speakers

## Response Style in Voice Mode

```
✅ "Done."
✅ "Opening VS Code."
✅ "Print is 63% complete, about 42 minutes left."
✅ "I can cancel the print. Confirm?"

❌ "Sure! I'd be happy to help you open VS Code right now!"
```

## Notes

- Shorter responses required in voice mode — config-controlled max length
- Provider should be swappable via config without code changes
- Barge-in: if user speaks while KOBE is talking, TTS stops immediately
