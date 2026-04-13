# 🎙️ Wake Service

> **Phase 1** · Status: 🔲 Not started

Listens for wake words and triggers the voice pipeline.

---

## Responsibilities

- Always-on wake word detection
- Support "Hey KOBE" and "OK KOBE"
- Software mute / unmute toggle
- Minimize false positives
- Pass activation signal to `stt_service`

## Technology

| Component | Choice |
|-----------|--------|
| Wake word engine | [OpenWakeWord](https://github.com/dscripka/openWakeWord) |
| Custom wake phrase | "Hey KOBE" / "OK KOBE" |
| Mute modes | Software mute + future physical button |

## Inputs / Outputs

- **Input:** Continuous microphone audio stream
- **Output:** Wake event → triggers `stt_service`

## Notes

- Must support always-on and manual (push-to-talk) modes
- Should be pauseable during TTS playback to prevent re-triggering
- Physical mute button support scaffolded here (Phase 6: MuteMe Mini)
