# Project KOBE — Budget

> All prices in **Canadian dollars (CAD)**. USD converted at **1 USD = 1.39 CAD** (April 2026).
> Prices sourced from Canadian retailers (Best Buy CA, Amazon CA, Walmart CA, Logitech CA) as of April 2026.

---

## Hardware Budget

### Required Hardware (You Already Have)

| Item | Notes | Est. Value |
|------|-------|-----------|
| Windows PC | RTX 3060, primary compute node | — (owned) |
| Second monitor | Dedicated KOBE HUD display | — (owned) |
| USB microphone | Voice input | — (owned) |
| Dedicated speakers | TTS output | — (owned) |
| Bambu Lab P1S | 3D printer integration target | — (owned) |

---

### Phase 5 — Gesture Control Hardware

| Item | Retailer | Price (CAD) |
|------|----------|------------|
| Logitech C922 Pro Stream Webcam | Logitech CA / Best Buy CA | ~$149.99 |
| **Phase 5 Subtotal** | | **~$150** |

> **Note:** A cheaper 1080p webcam (~$40–60 CAD) will work for MediaPipe gesture tracking if you don't need streaming quality.

---

### Phase 6 — Physical Controls (Optional)

| Item | Retailer | Price (CAD) |
|------|----------|------------|
| USB desk mute button (e.g. MuteKeys) | Amazon CA / Etsy CA | ~$50–75 |
| **Phase 6 Subtotal** | | **~$65** |

---

### Phase 7 — Holographic Fan

| Item | Retailer | Price (CAD) |
|------|----------|------------|
| 65cm WiFi holographic fan (budget tier, e.g. Walmart CA) | Walmart CA | ~$235–260 |
| 65cm WiFi holographic fan (mid-range) | Amazon CA | ~$300–400 |
| 65cm Ultra Series (Holofex, premium) | holofex.com | ~$794–993 |
| **Phase 7 Subtotal (budget pick)** | | **~$250** |

> **Recommendation:** Start with the ~$250 Walmart CA budget tier to validate use case before upgrading.

---

### Total Hardware Estimate

| Scope | Estimated Cost (CAD) |
|-------|---------------------|
| Phase 5 (webcam) | ~$150 |
| Phase 6 (mute button) | ~$65 |
| Phase 7 (holographic fan, budget) | ~$250 |
| **Total new hardware** | **~$465** |
| **vs. ~$1,000 CAD budget** | **✅ ~$535 under budget** |

---

## Software / API Monthly Costs

### Free / Already Covered

| Service | Cost | Notes |
|---------|------|-------|
| OpenWakeWord | Free | Local, open source |
| faster-whisper (STT) | Free | Local, GPU-accelerated on RTX 3060 |
| MediaPipe Hands | Free | Local gesture tracking |
| OpenClaw | Free | Self-hosted |
| Claude via GitHub Copilot Pro+ | Already paying | No extra cost |
| FreeCAD | Free | Open source CAD |
| Discord bot | Free | Alerts only |

---

### Paid Services

| Service | Plan | Cost (USD/mo) | Cost (CAD/mo) | Notes |
|---------|------|--------------|--------------|-------|
| ElevenLabs TTS | Starter | $5 USD | ~$7 CAD | 30,000 chars/mo — light use |
| ElevenLabs TTS | Creator | $11 USD | ~$15 CAD | 100,000 chars/mo — recommended |
| ElevenLabs TTS | Pro | $99 USD | ~$138 CAD | 500,000 chars/mo — heavy use |
| OpenAI TTS (backup) | Pay-per-use | ~$15 USD | ~$21 CAD | At ~$0.015/1k chars, ~1M chars/mo |

> **Recommendation:** Start with **ElevenLabs Creator (~$15 CAD/mo)**. 100k characters covers roughly 70,000–80,000 words of spoken output per month — more than enough for daily assistant use.

---

### Monthly Cost Summary

| Scenario | CAD/month |
|----------|----------|
| Minimal (ElevenLabs Starter) | ~$7 |
| **Recommended (ElevenLabs Creator)** | **~$15** |
| Heavy use (ElevenLabs Pro) | ~$138 |
| **vs. ~$75 CAD/mo budget** | **✅ Well within budget** |

---

## Full Budget Summary

| Category | Est. Cost (CAD) |
|----------|----------------|
| New hardware (all phases) | ~$465 one-time |
| Monthly API costs (recommended) | ~$15/month |
| **Year 1 total estimate** | **~$645** |
| **Lambert's budget** | ~$1,000 hardware + $75/mo = ~$1,900/yr |
| **Status** | **✅ Comfortably within budget** |

---

## Notes

- All hardware is optional and phase-gated — you only spend when you reach that phase
- Local STT and wake word cost $0 — your RTX 3060 handles it
- ElevenLabs Creator at ~$15 CAD/mo is the only real ongoing cost
- Smart home devices (lights, etc.) not budgeted yet — prices vary widely
- Bambu P1S integration has no additional cost (local API access)
