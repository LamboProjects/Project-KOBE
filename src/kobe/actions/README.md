# ⚙️ Actions

> **Phase 1–3** · Status: ✅ Built

Central action dispatcher + spoken confirmation for destructive commands.

---

## What's built

- `executor.py` — `run_action_service(bus, settings)` consumes `ActionRequested` and dispatches:
  - Generic verbs (`open_app`, `open_url`, `noop`) handled locally, with an allowlist.
  - Everything else re-published on an inner namespaced topic so the owning integration (`bambu_*`, `spotify_*`, `steam_*`, `screen_inspect`, windows control from `automation/windows_ctrl.py`) handles it without a double-dispatch.
  - Emits `ActionCompleted(ok, summary)` for HUD + TTS surfacing.
- `confirmation.py` — `run_confirmation_service(bus, settings)` turns `ConfirmationRequested` into a TTS challenge ("I can cancel the print. Confirm?"), waits for the next `TranscriptReady`, runs a yes/no classifier, and emits `ConfirmationResult(approved)`. Sequential (one challenge at a time) so we don't stack prompts.

## Example voice commands

```
"Hey KOBE, open Spotify"        → open_app (generic)
"Hey KOBE, open VS Code"        → open_app (generic)
"OK KOBE, volume up"            → windows_ctrl (pycaw)
"Hey KOBE, pause the print"     → ConfirmationRequested → bambu_pause
"OK KOBE, launch Cyberpunk"     → steam_launch_game (alias → appid)
"Hey KOBE, what's on my screen?" → screen_inspect (vision service)
```

## Confirmation policy

- Anything that mutates the printer (pause, resume, cancel) goes through `ConfirmationRequested` first.
- Future: closing apps with unsaved-work risk (VS Code, FreeCAD, Bambu Studio) will wire through the same flow.

## Inputs / Outputs

- **Input:** `ActionRequested(verb, args)`, `ConfirmationRequested(verb, args, prompt)`, `TranscriptReady` (while a confirmation is pending)
- **Output:** Dispatches work to `integrations/*` or `automation/windows_ctrl.py`; emits `ActionCompleted` and `ConfirmationResult`
