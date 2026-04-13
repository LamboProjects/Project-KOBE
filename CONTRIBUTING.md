# 🤝 Contributing to Project KOBE

> This is Lambert's private personal project. These notes are for future-Lambert during development.

---

## 🌿 Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | ✅ Stable, working code only — never break this |
| `dev` | 🔨 Active development branch |
| `phase/N-name` | 📦 Phase-specific feature branches (e.g. `phase/1-voice`) |
| `fix/description` | 🐛 Bug fixes |

**Flow:** `phase/N → dev → main`

---

## ✍️ Commit Style

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add wake word detection service
fix: resolve TTS playback cutoff on barge-in
docs: update Phase 1 checklist in ROADMAP
chore: clean up config defaults
refactor: split stt_service into capture + transcribe
test: add unit tests for confirmation_manager
```

---

## 📦 Adding a New Module

1. Create folder under `src/<module-name>/`
2. Add a `README.md` inside it (describe purpose, inputs, outputs, phase)
3. Wire it into `ROADMAP.md` under the correct phase
4. Add tests under `tests/<module-name>/`
5. Update `docs/ARCHITECTURE.md` module table

---

## ⚙️ Config

- All environment-specific settings go in `config/`
- **Never commit API keys or tokens** — use `.env` files (gitignored)
- ElevenLabs, OpenAI, Discord, Bambu, GitHub credentials must stay out of source control

---

## 🧪 Testing

- Each module should have a test folder under `tests/`
- Unit tests preferred — keep integration tests isolated
- Before merging to `main`: all tests pass ✅
