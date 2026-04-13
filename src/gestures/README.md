# 👋 Gesture Service

> **Phase 5** · Status: 🔲 Not started

Enables hand gesture control of KOBE via webcam.

---

## Responsibilities

- Capture webcam feed continuously
- Detect and classify hand gestures using MediaPipe
- Translate gestures into KOBE commands
- Provide gesture feedback on HUD
- Notify `conversation_router` or `hud_frontend` of gesture events

---

## Hardware

| Item | Spec | Price (CAD) |
|------|------|------------|
| Logitech C922 Pro | 1080p, autofocus, reliable driver support | $113.98 |

---

## Technology

| Component | Choice |
|-----------|--------|
| Gesture engine | [MediaPipe Hands](https://mediapipe.dev) |
| Language | Python |
| Camera API | OpenCV |

---

## Gesture Set (Phase 5 — Keep it Small)

| Gesture | Action |
|---------|--------|
| Swipe left ← | Previous HUD panel |
| Swipe right → | Next HUD panel |
| Point + hold | Select / confirm |
| Open palm push | Dismiss / back |
| Thumbs up | Confirm prompt |

> **Rule:** Reliability > variety. A small set that works every time beats an impressive set that misfires.

---

## Notes

- Gesture control supplements voice — never replaces it as primary input
- False positive mitigation: require gesture hold duration before triggering
- Gesture hints shown on HUD when webcam is active
- Phase 7: gestures also trigger holographic fan effects
