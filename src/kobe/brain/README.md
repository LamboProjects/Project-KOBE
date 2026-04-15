# 🧠 Brain Service

> **Phase 1** · Status: ✅ Built

Routes `TranscriptReady` text to OpenClaw over HTTP and emits `ResponseReady` + optional `ActionRequested` / `VisionRequested` / `ConfirmationRequested` events.

---

## What's built

- `router.py` — `run_brain_service(bus, settings)` consumes `TranscriptReady`, POSTs the transcript to `OPENCLAW_API_URL/v1/chat` with the bearer token, and publishes `ResponseReady` with the reply text.
- When `OPENCLAW_API_URL` is unset, the router falls back to a local **echo stub** that still mimics the contract — lets the rest of the pipeline run end-to-end without a VPS.
- Action intent parsing lives next to the router: verbs like `open_app`, `open_url`, `bambu_status`, `spotify_*`, `steam_launch_game`, `screen_inspect` become `ActionRequested` events; destructive ones (`bambu_cancel`, `bambu_pause`) go through `ConfirmationRequested` first.

## Responsibilities

- Receive transcribed text from `stt_service`
- Call OpenClaw for the reply (or fall back to the echo stub)
- Emit `ResponseReady` for TTS + HUD
- Emit `ActionRequested` / `VisionRequested` / `ConfirmationRequested` for downstream services

## Technology

| Component | Choice |
|-----------|--------|
| Agent framework | [OpenClaw](../../../docs/OPENCLAW.md) over HTTP (`/v1/chat`) |
| AI model | Claude Sonnet 4.6 (hosted by OpenClaw) |
| Memory | OpenClaw session memory (server-side) |
| Offline fallback | Local echo stub in `router.py` |

## Voice response rules

- 1–2 sentences max in voice mode
- No filler ("Sure!", "Absolutely!", "Great question!")
- Destructive actions go through `confirmation_manager`
- Dry wit allowed, sparingly

## Inputs / Outputs

- **Input:** `TranscriptReady(text)` on the bus
- **Output:** `ResponseReady(text)`, plus zero-or-more `ActionRequested` / `VisionRequested` / `ConfirmationRequested`
