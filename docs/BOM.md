# Project KOBE — Bill of Materials (BOM)

> All prices in **Canadian dollars (CAD)**.
> USD converted at **1 USD = 1.39 CAD** (April 2026 rate).
> Prices verified from Canadian retailers as of April 13, 2026.
> Items marked ✅ are already owned. Items marked 🛒 need to be purchased.

---

## Already Owned (No Cost)

| # | Item | Purpose | Estimated Value |
|---|------|---------|----------------|
| 1 | Windows 11 PC (RTX 3050 Ti Laptop, 4 GB VRAM) | Main compute node — STT, wake word, HUD, automation | — (owned) ✅ |
| 2 | Second monitor | Dedicated KOBE HUD display | — (owned) ✅ |
| 3 | USB microphone | Voice input | — (owned) ✅ |
| 4 | Dedicated speakers | TTS audio output | — (owned) ✅ |
| 5 | Bambu Lab P1S | 3D printer — integration target | — (owned) ✅ |

---

## Phase 5 — Gesture Control Hardware

| # | Item | Spec | Retailer | SKU / ASIN | Price (CAD) | Phase |
|---|------|------|---------|-----------|------------|-------|
| 6 | Logitech C922 Pro Stream Webcam | 1080p/30fps, 720p/60fps, autofocus, dual mic, tripod included | Amazon CA | B01MTTMPKT | **$113.98** | Phase 5 🛒 |

> **Budget alternative:** Any 1080p webcam ($35–60 CAD) will work for MediaPipe gesture tracking if streaming quality isn't needed.

---

## Phase 6 — Physical Controls

| # | Item | Spec | Retailer | SKU / ASIN | Price (CAD) | Phase |
|---|------|------|---------|-----------|------------|-------|
| 7 | MuteMe Mini (USB-A) | Illuminated physical mute button, toggle/PTT/push-to-mute modes, Windows/Mac | Amazon CA | B0CCV1CYVD | **$40.58** | Phase 6 🛒 |

> **Alternatives:**
> - Elgato Stream Deck Mini (6 LCD keys, $84.99 — Canada Computers) — more versatile, macro buttons for KOBE commands
> - MuteMe Mini USB-C version — same price, USB-C connector

---

## Phase 7 — Holographic Fan

| # | Item | Spec | Retailer | Price (CAD) | Phase |
|---|------|------|---------|------------|-------|
| 8a | 65cm Holographic Fan (budget) | 768 LED, WiFi/App, 8GB TF card | Walmart CA | **$258.75** | Phase 7 🛒 |
| 8b | 65cm Holographic Fan (alt) | Higher resolution variant | Amazon CA | **~$300–400** | Phase 7 🛒 |
| 8c | HoloFex HoloU65 Ultra (premium) | 1600×768, sync support, commercial grade | holofex.com | **$794** | Phase 7 🛒 |

> **Recommendation:** Start with the Walmart CA budget unit (~$259) to validate use case and content pipeline before upgrading.

---

## Software & APIs (Monthly Recurring)

| # | Service | Plan | USD/mo | CAD/mo | Notes |
|---|---------|------|--------|--------|-------|
| S1 | OpenWakeWord | Free | $0 | $0 | Local, open source |
| S2 | faster-whisper (STT) | Free | $0 | $0 | Local, GPU on RTX 3050 Ti (`base.en`, int8_float16) |
| S3 | MediaPipe Hands | Free | $0 | $0 | Local gesture tracking |
| S4 | FreeCAD | Free | $0 | $0 | Open source CAD |
| S5 | OpenClaw | Free | $0 | $0 | Self-hosted on VPS |
| S6 | Claude (via GitHub Copilot Pro+) | Already paying | $0 extra | $0 extra | No additional cost |
| S7 | Discord bot (alerts) | Free | $0 | $0 | No cost for basic bot usage |
| **S8** | **ElevenLabs TTS — Creator** | **Recommended** | **$11 USD** | **~$15** | **100k chars/mo — daily assistant use** |
| S9 | ElevenLabs TTS — Starter (light) | Minimal | $5 USD | ~$7 | 30k chars/mo — backup/testing |
| S10 | OpenAI TTS (backup) | Pay-per-use | ~$0.015/1k chars | ~$0.021/1k | Fallback only |

---

## Full BOM Summary

### One-Time Hardware Costs

| Phase | Item | CAD |
|-------|------|-----|
| Phase 5 | Logitech C922 Webcam | $113.98 |
| Phase 6 | MuteMe Mini USB-A | $40.58 |
| Phase 7 | 65cm Holographic Fan (Walmart, budget) | $258.75 |
| **Total new hardware** | | **$413.31** |

### Monthly Software Costs (Recommended)

| Service | CAD/mo |
|---------|--------|
| ElevenLabs Creator | ~$15 |
| Everything else | $0 |
| **Total/month** | **~$15** |

### Year 1 Total Cost Estimate

| Category | Cost |
|----------|------|
| Hardware (all phases) | ~$413 one-time |
| Software (12 months × $15) | ~$180/yr |
| **Year 1 total** | **~$593 CAD** |
| Lambert's hardware budget | ~$1,000 CAD |
| Lambert's monthly API budget | ~$75/mo = ~$900/yr |
| **Total budget** | **~$1,900/yr** |
| **Remaining budget** | **~$1,307 CAD** |
| **Status** | **✅ Well within budget** |

---

## Notes

- All hardware is phase-gated — only spend when you hit that phase
- RTX 3050 Ti handles local AI (STT, wake word, gesture) = $0 AI compute cost; screen vision calls out to gpt-4o-mini / OpenClaw
- The only real ongoing cost is ElevenLabs ~$15/mo for polished TTS
- Smart home devices (Phase 6+) are not included — prices vary
- Prices may change; refresh before purchasing

---

## Purchase Links (April 2026)

| Item | Link |
|------|------|
| Logitech C922 | [amazon.ca/dp/B01MTTMPKT](https://www.amazon.ca/dp/B01MTTMPKT) |
| MuteMe Mini USB-A | [amazon.ca/dp/B0CCV1CYVD](https://www.amazon.ca/dp/B0CCV1CYVD) |
| Holographic Fan (Walmart) | [walmart.ca](https://www.walmart.ca/en/ip/3D-Hologram-Fan-65cm-Holographic-Projector-Advertising-Display-768-LED-Beads-Support-WiFi-APP-Built-In-8GB-TF-Card-Business-Store-Signs-Bar-Casino-Pa/5U6OA7ZTPQPZ) |
| ElevenLabs Creator | [elevenlabs.io/pricing](https://elevenlabs.io/pricing) |
