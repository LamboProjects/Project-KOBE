# 🔒 Security Policy

---

## 🚨 Secrets — Never Commit These

The following must **never** appear in source control:

| Secret | Where to Store |
|--------|---------------|
| ElevenLabs API key | `.env` file (gitignored) |
| OpenAI API key | `.env` file (gitignored) |
| GitHub token | `.env` file (gitignored) |
| Discord bot token | `.env` file (gitignored) |
| Bambu Cloud credentials | `.env` file (gitignored) |
| OpenClaw config | Local config only |

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
