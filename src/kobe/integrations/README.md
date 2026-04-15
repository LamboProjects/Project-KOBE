# 🔌 Integrations

> **Phase 3** · Status: ✅ Built

External-service bridges. Each lives in a single module and talks to the rest of the system via the event bus.

---

## What's built

- `bambu.py` — **Bambu Lab P1S** over LAN MQTT (`paho-mqtt` v2). Subscribes to the printer's push topic, publishes `PrinterStatus` (progress, stage, temps, remaining, AMS) and `PrinterAlert` (started / completed / failed / paused) onto the bus. Handles `bambu_status` (returns a TTS-ready summary) and the confirmation-gated `bambu_pause` / `bambu_resume` / `bambu_cancel` commands. Needs `BAMBU_HOST`, `BAMBU_SERIAL`, `BAMBU_ACCESS_CODE`.
- `spotify.py` — **Spotify** via `spotipy`. Play / pause / next / previous / volume, plus a polling loop that emits `NowPlayingChanged` for the HUD. Needs `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` (user auth on first run).
- `steam.py` — **Steam** game launch by voice. Maps spoken names through an alias map to an app id and spawns `steam://rungameid/<id>`. No creds required.
- `discord.py` — **Discord alerts** via webhook (`DISCORD_WEBHOOK_URL`). Listens for `PrinterAlert`, dedupes within a 3 s window, posts a color-coded embed. Never posts anything else — strictly one-way alerts.

## Bus contract

| Integration | Consumes | Publishes |
|-------------|----------|-----------|
| `bambu` | `ActionRequested(bambu_*)`, `ConfirmationResult` | `PrinterStatus`, `PrinterAlert`, `ActionCompleted` |
| `spotify` | `ActionRequested(spotify_*)` | `NowPlayingChanged`, `ActionCompleted` |
| `steam` | `ActionRequested(steam_launch_game)` | `ActionCompleted` |
| `discord` | `PrinterAlert` | (outbound HTTP only) |

## Notes

- All credentials come from `config/.env` — see `SECURITY.md` for the full list
- Integrations never touch the HUD directly; the HUD relays from `bus → ws`
- Smart plug / lights integration is still planned for Phase 6
