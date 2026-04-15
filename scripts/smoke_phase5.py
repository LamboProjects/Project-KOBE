"""Phase 5 smoke test.

Exercises the gesture pipeline without touching a real webcam or MediaPipe.
We feed synthetic FrameResults straight into a `GestureClassifier` and a
slim test harness around `run_gesture_service` (which we don't run end-to-end
since it owns a real cv2.VideoCapture). Coverage:

1. **Pretrained → KOBE static gestures.** Pushing N frames of `Thumb_Up` into
   the classifier emits a `confirm` event; another N of `Closed_Fist` emits
   `dismiss`; another N of `Pointing_Up` emits `point`.
2. **Swipe motion detection.** Synthesizing landmark-9 coordinates moving
   right-to-left at the threshold velocity emits `swipe_left`; mirror for right.
3. **Cooldown.** A second consecutive `confirm` within the cooldown window is
   suppressed.
4. **Hand-absence handling.** A "no hand" frame in the middle of a static
   sequence shouldn't crash and shouldn't fire.
5. **HUD action mapping shape.** Verify the service module's
   `_GESTURE_ACTION_MAP` exposes the expected `hud_*` action names.

Runs anywhere with the deps installed; no GPU, no webcam, no API keys.
"""
from __future__ import annotations

import sys
import time

import structlog

from kobe.config import load_settings
from kobe.gestures.camera import FrameResult
from kobe.gestures.classifier import GestureClassifier
from kobe.logging import configure_logging


def _frame(label: str, score: float, ts: int, *, hand: str = "Right",
           landmarks: list[tuple[float, float, float]] | None = None) -> FrameResult:
    if landmarks is None:
        # Provide 21 dummy landmarks centered at (0.5, 0.5) so swipe state
        # accumulates a stable palm position when we want to test STATIC
        # gestures (no swipe should fire from a still hand).
        landmarks = [(0.5, 0.5, 0.0)] * 21
    return FrameResult(
        timestamp_ms=ts,
        landmarks=landmarks,
        gesture_label=label,
        gesture_score=score,
        handedness=hand,
    )


def _swipe_landmarks(x_at_9: float) -> list[tuple[float, float, float]]:
    """21 landmarks with index 9 placed at (x_at_9, 0.5)."""
    pts = [(0.0, 0.0, 0.0)] * 21
    pts[9] = (x_at_9, 0.5, 0.0)
    return pts


def main() -> int:
    configure_logging("INFO")
    log = structlog.get_logger("smoke5")

    settings = load_settings()
    settings.gesture_static_window = 6
    settings.gesture_static_required = 5
    settings.gesture_min_score = 0.6
    settings.gesture_swipe_window = 10
    settings.gesture_swipe_lookback = 5
    settings.gesture_swipe_dx_threshold = 0.18
    settings.gesture_swipe_dy_max = 0.08
    settings.gesture_swipe_required_frames = 3
    settings.gesture_cooldown_ms = 1200

    classifier = GestureClassifier(settings)

    # --- Test 1: Thumb_Up over a window → "confirm".
    fired_confirm = []
    for i in range(8):
        events = classifier.push(_frame("Thumb_Up", 0.9, ts=i * 30))
        fired_confirm.extend(events)
    confirms = [e for e in fired_confirm if e.name == "confirm"]
    assert confirms, f"Thumb_Up sequence didn't emit confirm: {fired_confirm}"
    log.info("test_1a_pass_thumb_up_confirm", confidence=confirms[0].confidence)

    # Cooldown: a second Thumb_Up immediately after must NOT fire again.
    fired2 = []
    for i in range(8):
        events = classifier.push(_frame("Thumb_Up", 0.9, ts=300 + i * 30))
        fired2.extend(events)
    assert not any(e.name == "confirm" for e in fired2), (
        f"cooldown failed: {fired2}"
    )
    log.info("test_1b_pass_confirm_cooldown")

    # --- Test 2: Closed_Fist → "dismiss" (after enough time for the cooldown).
    classifier.reset()
    fired_dismiss = []
    for i in range(8):
        events = classifier.push(_frame("Closed_Fist", 0.85, ts=10_000 + i * 30))
        fired_dismiss.extend(events)
    assert any(e.name == "dismiss" for e in fired_dismiss), fired_dismiss
    log.info("test_2_pass_closed_fist_dismiss")

    # --- Test 3: Pointing_Up → "point".
    classifier.reset()
    fired_point = []
    for i in range(8):
        events = classifier.push(_frame("Pointing_Up", 0.8, ts=20_000 + i * 30))
        fired_point.extend(events)
    assert any(e.name == "point" for e in fired_point), fired_point
    log.info("test_3_pass_point")

    # --- Test 4: Hand absence in the middle of a static run must reset the
    # static window — the user has to release and reform the gesture.
    # Sequence: 2 Thumb_Up, 1 NO HAND, 4 Thumb_Up. Without the no-hand reset,
    # the window would still have 5 of 6 "confirm" votes and fire. With the
    # reset, the post-gap Thumb_Up frames must hit the required count from
    # zero — 4 Thumb_Up is one short, so NO confirm should fire.
    classifier.reset()
    fired = []
    seq = [("Thumb_Up", 0.9), ("Thumb_Up", 0.9), ("", 0.0),
           ("Thumb_Up", 0.9), ("Thumb_Up", 0.9), ("Thumb_Up", 0.9),
           ("Thumb_Up", 0.9)]
    for i, (label, score) in enumerate(seq):
        if label:
            fr = _frame(label, score, ts=30_000 + i * 30)
        else:
            fr = FrameResult(
                timestamp_ms=30_000 + i * 30,
                landmarks=[],
                gesture_label="",
                gesture_score=0.0,
                handedness="",
            )
        fired.extend(classifier.push(fr))
    confirms_after_gap = [e for e in fired if e.name == "confirm"]
    assert not confirms_after_gap, (
        f"no-hand gap should reset static window; got {confirms_after_gap}"
    )
    log.info("test_4_pass_no_hand_resets_static_vote", total_events=len(fired))

    # --- Test 5: Swipe LEFT — landmark 9 moves from x=0.85 to x=0.15.
    classifier.reset()
    fired_swipe_l = []
    # 12 frames moving from right (0.85) to left (0.15). dx per frame ≈ -0.064.
    # With lookback=5, the 5-frame dx ≈ -0.32, well below threshold of -0.18.
    for i in range(12):
        x = 0.85 - i * (0.70 / 11.0)
        fr = FrameResult(
            timestamp_ms=40_000 + i * 30,
            landmarks=_swipe_landmarks(x),
            gesture_label="",  # no static gesture; pure motion
            gesture_score=0.0,
            handedness="Right",
        )
        fired_swipe_l.extend(classifier.push(fr))
    swipes_l = [e for e in fired_swipe_l if e.name == "swipe_left"]
    assert swipes_l, f"swipe_left didn't fire: {fired_swipe_l}"
    log.info("test_5a_pass_swipe_left", confidence=swipes_l[0].confidence)

    # --- Test 6: Swipe RIGHT — mirror.
    classifier.reset()
    fired_swipe_r = []
    for i in range(12):
        x = 0.15 + i * (0.70 / 11.0)
        fr = FrameResult(
            timestamp_ms=50_000 + i * 30,
            landmarks=_swipe_landmarks(x),
            gesture_label="",
            gesture_score=0.0,
            handedness="Right",
        )
        fired_swipe_r.extend(classifier.push(fr))
    swipes_r = [e for e in fired_swipe_r if e.name == "swipe_right"]
    assert swipes_r, f"swipe_right didn't fire: {fired_swipe_r}"
    log.info("test_5b_pass_swipe_right", confidence=swipes_r[0].confidence)

    # --- Test 7: HUD action map shape.
    from kobe.gestures import service as gs
    action_map = getattr(gs, "_GESTURE_ACTION_MAP", None) or getattr(gs, "GESTURE_ACTION_MAP", None)
    assert action_map is not None, "service must expose a gesture→action map"
    expected_pairs = {
        "swipe_left":  "hud_navigate_prev",
        "swipe_right": "hud_navigate_next",
        "point":       "hud_select",
        "confirm":     "hud_confirm",
        "dismiss":     "hud_dismiss",
    }
    for k, v in expected_pairs.items():
        assert action_map.get(k) == v, f"action map mismatch for {k}: {action_map.get(k)!r}"
    log.info("test_6_pass_action_map")

    log.info("smoke_phase5_ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
