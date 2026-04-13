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

## Configuration (Phase 1)

When building the local voice pipeline, configure `brain/conversation_router` to hit the OpenClaw API:

```env
# config/.env
OPENCLAW_API_URL=https://<your-vps-hostname>
OPENCLAW_API_KEY=<your-openclaw-token>
OPENCLAW_AGENT=main
```

The local pipeline sends transcribed text → OpenClaw returns the response text → TTS speaks it.

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
| OpenClaw as brain for voice pipeline | 🔲 Phase 1 — configure when building |
| API endpoint hardened for local network | 🔲 Phase 1 |
