# 👋 Gesture Service

> **Phase 5** · Status: ✅ Built

Hand-gesture control of KOBE via the C922 webcam, driven by MediaPipe Tasks in `LIVE_STREAM` mode.

---

## What's built

- `camera.py` — `cv2.VideoCapture(idx, CAP_DSHOW)` with a 1-frame buffer to avoid stale frames, plus MediaPipe Tasks `GestureRecognizer` in `LIVE_STREAM` mode on a dedicated producer thread. Auto-downloads the `gesture_recognizer.task` model. Bridges back into asyncio via `loop.call_soon_threadsafe`. Tracks FPS + connectivity health.
- `classifier.py` — pure deque-based recognizers:
  - **Swipe left/right** — landmark-9 motion buffer + lookback dx threshold + consecutive-frame voting
  - **Point** — pretrained `Pointing_Up`
  - **Confirm** — pretrained `Thumb_Up` / `Open_Palm`
  - **Dismiss** — pretrained `Closed_Fist` / `Thumb_Down` + custom shake detector
  - Per-name cooldowns, static-vote debounce, no-hand resets, held-pose can't re-fire across cooldown, shake suppresses spurious swipe.
- `service.py` — `run_gesture_service(bus, settings)` wires camera → classifier → bus. Mute-aware (drains its queue on `MuteToggled`), maps gestures to HUD nav actions, publishes `GestureDetected(name, confidence)` and `WebcamStatus` telemetry every 2 s.

## Hardware

| Item | Spec | Price (CAD) |
|------|------|------------|
| Logitech C922 Pro | 1080p/30, autofocus, reliable driver support | $113.98 |

## Setup

```bash
uv sync --extra gestures   # installs mediapipe + the cv2 it ships with
```

`mediapipe` is an optional extra in `pyproject.toml` so non-gesture installs don't pull a webcam-capable wheel.

## Gesture set

| Gesture | Action |
|---------|--------|
| Swipe left ← | Previous HUD panel (`data-focused` cycle) |
| Swipe right → | Next HUD panel |
| Point (hold) | Select / confirm (flash) |
| Thumb up / Open palm | Confirm prompt |
| Closed fist / Thumb down / Shake | Dismiss (clears focus) |

## Privacy

- No camera frames or hand landmarks ever hit the HUD — only the recognised semantic gesture name + confidence.
- Service drains the pending-gesture queue while muted, so nothing leaks from a muted session.

## Inputs / Outputs

- **Input:** C922 video via cv2; `MuteToggled` events
- **Output:** `GestureDetected(name, confidence)`, `WebcamStatus` on the bus
