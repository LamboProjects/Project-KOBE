# 🔒 Security Policy

---

## 🚨 Secrets — Never Commit These

The following must **never** appear in source control:

| Secret | Env var | Where to Store |
|--------|---------|---------------|
| ElevenLabs API key | `ELEVENLABS_API_KEY` | `config/.env` (gitignored) |
| OpenAI API key (TTS fallback + vision) | `OPENAI_API_KEY` | `config/.env` (gitignored) |
| OpenClaw API key + URL | `OPENCLAW_API_KEY`, `OPENCLAW_API_URL` | `config/.env` (gitignored) |
| Bambu P1S LAN access code + serial | `BAMBU_ACCESS_CODE`, `BAMBU_SERIAL` | `config/.env` (gitignored) |
| Spotify app credentials | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | `config/.env` (gitignored) |
| Discord alert webhook | `DISCORD_WEBHOOK_URL` | `config/.env` (gitignored) |
| GitHub token (workflows only) | `GITHUB_TOKEN` | `.env` file (gitignored) |

See `config/.env.example` for the full template.

---

## 🛡️ Best Practices

- All secrets via `.env` — never hardcoded, never committed
- Rotate any token that accidentally gets committed immediately
- Keep `.gitignore` up to date — `*.env`, `config/secrets.*`, `*.key`
- Don't log secrets, even in debug output

---

## 🐛 Reporting Issues

This is a private repository. If you discover a security issue:

1. Do **not** open a public issue
2. Fix it in a private branch
3. Rotate any affected credentials before merging

---

## 📋 Dependency Audits

When adding new packages:
- Check for known CVEs
- Prefer well-maintained packages with recent commits
- Run `npm audit` / `pip-audit` before committing new dependencies
