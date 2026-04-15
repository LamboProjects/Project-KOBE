# 🔌 Integrations

> **Phase 3** · Status: 🔲 Not started

Connects KOBE to external apps and services.

---

## Integration Targets

| Integration | Purpose | Priority |
|-------------|---------|---------|
| 🖨️ **Bambu Lab P1S** | Print status, alerts, pause/resume/cancel | 🔴 High |
| 🎵 **Spotify** | Playback control, now-playing HUD | 🔴 High |
| 🎮 **Steam** | Game launch by voice | 🟡 Medium |
| 💬 **Discord** | Printer alerts, event notifications | 🟡 Medium |
| 💡 **Smart Plug / Lights** | On/off control | 🟢 Low (Phase 6) |

---

## Bambu Lab P1S

**Must-have features:**
- `GET /status` → print progress, time remaining, AMS state, camera
- Alerts: print started, completed, failed, paused
- Control (with confirmation): pause, resume, cancel

**Dashboard fields:**
```
Print name         ████████░░ 82%
Time remaining     ~24 min
AMS / Filament     PLA White — Slot 1
Status             PRINTING
Camera             [live feed if feasible]
```

---

## Spotify

- Play / pause / next / previous
- Volume up / down
- Start named playlist by voice
- Now-playing widget on HUD
- Future: music-reactive holographic fan visuals

---

## Steam

- Launch game by name (`"Hey KOBE, launch Cyberpunk"`)
- List recent games
- Future: wishlist deal awareness

---

## Discord

- Webhook-based alerts (no full bot required for basic use)
- Events: print finished ✅, print failed ❌, print paused ⏸️
- Optional: voice channel experiments (Phase 6+)

---

## Notes

- Each integration lives in its own subfolder: `integrations/bambu/`, `integrations/spotify/`, etc.
- All credentials stored in `.env` — never hardcoded
- Integrations communicate via the internal event bus — not direct coupling to HUD
