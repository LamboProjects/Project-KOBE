# 🤖 OpenClaw Integration

> How KOBE connects to the OpenClaw AI backend running on Lambert's VPS.

---

## Overview

KOBE's intelligence layer does **not** run locally on the Windows PC. It routes to **OpenClaw** (self-hosted on a Hostinger VPS) which handles:

- Conversation context and memory
- Claude Sonnet 4.6 via GitHub Copilot Pro+
- Tool execution (calendar, Drive, integrations)
- Long-term memory (MEMORY.md, daily logs)

This is the same KOBE agent you're talking to right now on Telegram.

---

## Connection Architecture

```
[Windows PC — KOBE local pipeline]
        │
        │  HTTP / WebSocket
        ▼
[Hostinger VPS — OpenClaw]
        │
        ├── Claude Sonnet 4.6 (GitHub Copilot Pro+)
        ├── Memory (MEMORY.md, daily logs)
        ├── Tools (Drive, Calendar, GitHub, etc.)
        └── Skills (GitHub, printer, etc.)
```

---

## Configuration

The local pipeline reads OpenClaw settings from `config/.env`:

```env
# config/.env
OPENCLAW_API_URL=https://<your-vps-hostname>
OPENCLAW_API_KEY=<your-openclaw-token>
OPENCLAW_AGENT=main
```

When `OPENCLAW_API_URL` is blank, `src/kobe/brain/router.py` falls back to a built-in echo stub so the rest of the pipeline still works in dev.

### Expected HTTP endpoints

KOBE talks to OpenClaw over two endpoints on the same host:

| Endpoint | Phase | Who calls it | Request | Response |
|----------|-------|--------------|---------|----------|
| `POST /v1/chat` | 1 | `src/kobe/brain/router.py` | JSON: `{ "agent": "...", "request_id": "...", "text": "...", "persona_prompt": "..." }` + `Authorization: Bearer` | JSON reply the TTS service speaks |
| `POST /v1/vision` | 4 | `src/kobe/vision/backends.py` → `OpenClawBackend` | `multipart/form-data` with a JPEG field (`image`) plus the (optionally specialist-augmented) question | JSON: `{ "ok": bool, "text": str }` — consumed verbatim by `VisionResult`/`ResponseReady` |

Both calls stream back text KOBE either speaks directly or surfaces on the HUD vision panel.

### `/v1/chat` request body fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `agent` | str | yes | `settings.openclaw_agent` (defaults to `"main"`). |
| `request_id` | str | yes | Correlation id from the originating `TranscriptReady`. |
| `text` | str | yes | The user utterance. |
| `persona_prompt` | str | **optional; server may ignore** | Phase 6 persona prefix resolved from `settings.tts_persona_profile` via `src/kobe/brain/personas.py`. Presets: `default`, `concise`, `warm`, `terse`, `excited`. OpenClaw should treat this as a system-prompt prefix if supported; legacy servers that don't recognize the field should simply ignore it. |

---

## Why This Approach?

| Option | Pros | Cons |
|--------|------|------|
| ✅ Route through OpenClaw | Full memory, all tools, one brain | Needs VPS reachable from PC |
| ❌ Separate local LLM | Fully offline | No memory, no tools, weaker model |
| ❌ Direct Claude API | Simple | Costs extra, no memory, duplicate setup |

**OpenClaw is the right call** — you already have it running, it has your memory, preferences, and all your integrations baked in. KOBE on Windows is just the eyes, ears, and voice. The brain lives here.

---

## Workspace Access

OpenClaw (this agent) has the Project KOBE repo cloned at:

```
/data/.openclaw/workspace/Project-KOBE/
```

This means KOBE can:
- Edit files and push commits directly
- Review and update docs, roadmap, BOM
- Help write and review code for each phase
- Act as the AI pair programmer throughout the build

---

## Current Status

| Connection | Status |
|-----------|--------|
| Repo cloned to OpenClaw workspace | ✅ Done |
| `/v1/chat` wired into voice pipeline | ✅ Phase 1 — `src/kobe/brain/router.py` (echo stub when unconfigured) |
| `/v1/vision` wired into vision service | ✅ Phase 4 — `OpenClawBackend` in `src/kobe/vision/backends.py` |
| API endpoint hardened for local network | 🔲 Phase 6 (polish) |
