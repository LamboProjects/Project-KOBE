# Contributing to Project KOBE

This is a private personal project. Notes below are for Lambert's own reference during development.

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, working code only |
| `dev` | Active development |
| `phase/N-name` | Phase-specific feature branches |

---

## Commit Style

Use conventional commits:

```
feat: add wake word detection service
fix: resolve TTS playback cutoff on barge-in
docs: update Phase 1 checklist in ROADMAP
chore: clean up config defaults
```

---

## Adding a New Module

1. Create folder under `src/<module-name>/`
2. Add a `README.md` inside it describing what it does
3. Wire it into the relevant phase in `ROADMAP.md`
4. Add tests under `tests/<module-name>/`

---

## Config

All environment-specific settings go in `config/`. Never commit API keys or tokens — use `.env` files (gitignored).
