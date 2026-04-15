# 👁️ Screen Vision Service

> **Phase 4** · Status: ✅ Built

On-demand screen inspection — capture, route through an app-aware specialist prompt, send to a vision backend, and surface the answer on the HUD + TTS.

---

## What's built

- `capture.py` — `mss`-based screenshot. Supports `foreground`, `full`, or a `region=(x,y,w,h)` box. Region must be valid — never silently widens to the full screen.
- `backends.py` — `VisionBackend` Protocol returning `(ok, text)`. Built-in implementations:
  - `NullBackend` — stub for smoke tests (no network).
  - `OpenAIBackend` — gpt-4o-mini by default; JPEG over data URL.
  - `OpenClawBackend` — multipart POST to `${OPENCLAW_API_URL}/v1/vision` with the JPEG + question field.
  - Shared `encode_jpeg(shot, q, max_edge)` downsamples + JPEG-encodes so the uplink stays cheap.
- `context.py` — pure `detect_context(window_title) → WindowContext`. Ordered substring rules classify into **14** apps (`vscode`, `bambu_studio`, `freecad`, `fusion360`, `blender`, `obsidian`, `chrome`, `firefox`, `terminal`, `excel`, `slack`, `discord`, `explorer`) plus a `generic` fallback.
- `specialists.py` — per-app prompt augmentation. `augment_question(q, ctx)` prefixes app-specific framing and then appends the user's question. Skipped entirely for the `null` backend so smoke tests stay deterministic.
- `service.py` — `run_vision_service(bus, settings, backend)` consumes `VisionRequested` events or `ActionRequested("screen_inspect", {...})` from the brain, emits a `SCANNING…` marker, runs capture → augment → backend, and publishes `VisionResult(ok, summary, mode, context_name, …)` + `ResponseReady`.

## Trigger examples

```
"Hey KOBE, what's on my screen?"
"OK KOBE, summarize this page."
"Hey KOBE, what error is this?"
"OK KOBE, read the print settings."
"Hey KOBE, help me with this code."
```

## Privacy

- **On-demand only** — no passive screen monitoring.
- `image_path` is stripped from every WebSocket payload (cache + broadcast), so the HUD never receives a server-local file path.
- Images leave the machine only when `OpenAIBackend` or `OpenClawBackend` are in use.

## Inputs / Outputs

- **Input:** `VisionRequested` events, `ActionRequested("screen_inspect", {...})`
- **Output:** `VisionResult`, `ResponseReady` on the bus; HUD vision panel updates
