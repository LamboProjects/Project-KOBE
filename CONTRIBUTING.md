# 🤝 Contributing to Project KOBE

> This is Lambert's private personal project. These notes are for future-Lambert during development.
>
> **Current state:** Phases 1–5 are shipped on `origin/main`. Phase 6 (polish) and Phase 7 (holographic fan) are still ahead.

---

## 🌿 Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | ✅ Stable, working code only — never break this |
| `dev` | 🔨 Active development branch |
| `phase/N-name` | 📦 Phase-specific feature branches (e.g. `phase/6-polish`) |
| `fix/description` | 🐛 Bug fixes |

**Flow:** `phase/N → dev → main`

---

## ✍️ Commit Style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add wake word detection service
fix: resolve TTS playback cutoff on barge-in
docs: update Phase 5 checklist in ROADMAP
chore: clean up config defaults
refactor: split stt_service into capture + transcribe
test: add unit tests for confirmation_manager
```

---

## 📦 Repository Layout

Everything Python lives under `src/kobe/`:

```
src/kobe/
├── bus.py events.py config.py audio.py logging.py
├── wake/ stt/ tts/ brain/ actions/ mute/
├── hud/ system/ automation/
├── integrations/   ← bambu, spotify, steam, discord
├── vision/         ← capture, backends, context, specialists, service
└── gestures/       ← camera, classifier, service
```

Each service is a long-running `async def run_*_service(bus, settings, ...)` coroutine wired into the single `asyncio.TaskGroup` in `src/kobe/__main__.py`. Modules communicate only through the event bus — no direct imports across service boundaries.

### Adding a New Module

1. Create folder under `src/kobe/<module-name>/`
2. Add a `README.md` inside it (purpose, inputs/outputs, phase, file map)
3. Register events it produces/consumes in `src/kobe/events.py`
4. Wire its `run_*_service` coroutine into `src/kobe/__main__.py`
5. Add a row to the module table and event catalogue in `docs/ARCHITECTURE.md`
6. Add tests under `tests/<module-name>/` and, if it's a new phase, a `scripts/smoke_phase{N}.py`
7. Tick the checkbox in `ROADMAP.md`

---

## ⚙️ Config

- All environment-specific settings go in `config/`
- **Never commit API keys or tokens** — use `.env` files (gitignored)
- Current secrets surface: `ELEVENLABS_API_KEY`, `OPENAI_API_KEY`, `OPENCLAW_API_KEY` + `OPENCLAW_API_URL`, `BAMBU_ACCESS_CODE`, `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`, `DISCORD_WEBHOOK_URL`
- See `SECURITY.md` for the full secrets policy

---

## 🧪 Testing

- Each module has a folder under `tests/`; keep unit tests isolated from integration tests
- Smoke scripts under `scripts/smoke_phase{1,2,3,4,5}.py` run without a mic, speakers, webcam, or API keys
- Before merging to `main`: `uv run python scripts/smoke_phase*.py` all pass ✅
