# 🧠 Brain Service

> **Phase 1** · Status: 🔲 Not started

Routes user requests to Claude via OpenClaw and returns concise responses.

---

## Responsibilities

- Receive transcribed text from `stt_service`
- Maintain conversation context across turns
- Determine intent (conversation vs. action)
- Call `action_executor` for actionable commands
- Return voice-optimized response text to `tts_service`

## Technology

| Component | Choice |
|-----------|--------|
| Agent framework | [OpenClaw](https://openclaw.ai) |
| AI model | Claude Sonnet 4.6 (via GitHub Copilot Pro+) |
| Memory | OpenClaw session memory |
| Context | Lambert's profile, preferences, active state |

## Data Flow

```
stt_service → conversation_router → Claude via OpenClaw
                                          ↓
                                   response + action intent
                                          ↓
                          ┌───────────────┴──────────────┐
                          ↓                              ↓
                    action_executor                tts_service
```

## Voice Response Rules

- Always concise — 1-2 sentences max in voice mode
- No filler words ("Sure!", "Absolutely!", "Great question!")
- Confirmations before destructive actions
- Dry wit allowed occasionally

## Notes

- This module bridges OpenClaw (running on VPS) to the local Windows desktop pipeline
- Network latency to VPS must be minimized — local routing preferred where possible
- Fallback: if OpenClaw is unreachable, respond with a simple offline message
