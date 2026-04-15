# 👁️ Screen Vision Service

> **Phase 4** · Status: 🔲 Not started

Enables KOBE to inspect and understand what's currently on screen — on demand.

---

## Responsibilities

- Capture screenshot of active window or full screen on request
- Send image to vision model for analysis
- Return natural language summary to `conversation_router`
- Display result on HUD

---

## Trigger Examples

```
"Hey KOBE, what's on my screen?"
"OK KOBE, summarize this page."
"Hey KOBE, what error is this?"
"OK KOBE, read the print settings."
"Hey KOBE, help me with this code."
```

---

## Technology

| Component | Choice |
|-----------|--------|
| Screenshot | Windows `PIL` / `pyautogui` |
| Vision model | Claude Vision via OpenClaw |
| Scope | Active window or full screen (user-selectable) |

---

## High-Value Use Cases

| Context | Benefit |
|---------|---------|
| VS Code | Code help, error explanation |
| Bambu Studio | Print settings review |
| FreeCAD | CAD troubleshooting |
| Browser | Page summarization |
| Any app | Error message reading |

---

## Privacy & Scope

- **On-demand only** — KOBE never passively monitors the screen
- User must explicitly ask for screen inspection
- No continuous screen recording

---

## Notes

- Combine with active app detection (Phase 4) for smarter context-aware responses
- Image is sent to Claude Vision — ensure no sensitive information is in scope when triggered
- Response should be concise for voice delivery
