# ⚙️ Automation

> **Phase 1–3** · Status: 🔲 Not started

Handles PC-level automation — app launching, window management, volume, and desktop control.

---

## Responsibilities

- Launch applications by voice command
- Close apps (with confirmation for major apps)
- Focus / switch between windows
- Control system volume
- Control media playback (OS-level)
- Open websites or tools
- Future: file search, workflow macros, script execution

---

## Priority App Support

| App | Commands |
|-----|---------|
| Spotify | Open, play, pause, next |
| Steam | Open, launch game |
| VS Code | Open, open project |
| Bambu Studio | Open, check printer |
| FreeCAD | Open |
| Browser | Open URL |

---

## Example Voice Commands

```
"Hey KOBE, open Spotify"        → launches Spotify
"Hey KOBE, open VS Code"        → launches VS Code
"OK KOBE, volume up"            → increases system volume
"Hey KOBE, mute"                → mutes system audio
"OK KOBE, close Bambu Studio"   → closes (with confirmation)
"Hey KOBE, launch Cyberpunk"    → Steam game launch
```

---

## Confirmation Policy

The following actions require spoken confirmation before executing:

- Closing apps with unsaved work risk (VS Code, FreeCAD, Bambu Studio)
- Cancelling a print
- Any action flagged as destructive in config

---

## Notes

- Windows-first — uses `subprocess` / `pywin32` / `WScript` for automation
- App paths configurable (different machines may have different install locations)
- Volume control via Windows audio API
- Context-aware: if Spotify is already open, focus it instead of relaunching
