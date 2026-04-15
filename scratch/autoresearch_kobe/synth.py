"""Synthetic labeled-stream generator for gesture classifier autoresearch.

Emits deterministic `FrameResult` sequences with ground-truth expected and
forbidden events. Every call to `make_cases()` returns the same streams in the
same order so experiments are reproducible.

Design note: hand landmarks are collapsed to 21 copies of the palm centroid
(x, y, 0). The classifier only looks at landmark 9 (palm proxy) for motion
gestures and `bool(landmarks)` for presence, so per-finger accuracy is
irrelevant here. Static gestures are driven entirely by `gesture_label` +
`gesture_score` — again, the palm coordinates don't matter.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from kobe.gestures.camera import FrameResult


FPS = 30
FRAME_MS = 1000 // FPS  # 33 ms per frame, close to real MediaPipe cadence


def _lm(x: float, y: float) -> list[tuple[float, float, float]]:
    """21 identical (x, y, 0) landmarks — palm-only model."""
    return [(x, y, 0.0)] * 21


def frame(
    i: int,
    label: str,
    score: float,
    *,
    x: float = 0.5,
    y: float = 0.5,
    has_hand: bool = True,
    handedness: str = "Right",
) -> FrameResult:
    """Build one FrameResult at frame index `i` (timestamp = i * FRAME_MS)."""
    return FrameResult(
        timestamp_ms=i * FRAME_MS,
        landmarks=_lm(x, y) if has_hand else [],
        gesture_label=label,
        gesture_score=score,
        handedness=handedness,
    )


def _jit(i: int, seed: int, amplitude: float = 0.005) -> tuple[float, float]:
    """Deterministic per-frame jitter offset (dx, dy) from a (frame, seed) pair.

    Uses `random.Random` keyed on (seed, i) so cases are reproducible across
    runs. Default amplitude (~0.005) is well below the 0.18 swipe threshold
    over a single frame but accumulates enough to perturb the palm buffer.
    """
    rng = random.Random(seed * 1_000_003 + i)
    return (
        (rng.random() * 2 - 1) * amplitude,
        (rng.random() * 2 - 1) * amplitude,
    )


def frame_jittered(
    i: int,
    label: str,
    score: float,
    *,
    x: float = 0.5,
    y: float = 0.5,
    has_hand: bool = True,
    handedness: str = "Right",
    seed: int = 0,
    amplitude: float = 0.005,
) -> FrameResult:
    """Like `frame()` but adds seeded ±amplitude jitter to (x, y)."""
    dx, dy = _jit(i, seed, amplitude)
    return frame(
        i,
        label,
        score,
        x=x + dx,
        y=y + dy,
        has_hand=has_hand,
        handedness=handedness,
    )


@dataclass
class StreamCase:
    """One labeled stream. `expected_events` must fire in order within the
    given `[min_frame, max_frame]` windows. `forbidden_events` must NOT fire
    at any frame. `weight` scales this case's contribution to aggregate counts.
    """

    name: str
    frames: list[FrameResult]
    expected_events: list[tuple[str, int, int]]
    forbidden_events: list[str] = field(default_factory=list)
    weight: float = 1.0


_ALL_NAMES = ("confirm", "dismiss", "point", "swipe_left", "swipe_right")


def _forbid_all_except(*keep: str) -> list[str]:
    return [n for n in _ALL_NAMES if n not in keep]


def make_cases() -> list[StreamCase]:
    cases: list[StreamCase] = []

    # --- Static held positives ---------------------------------------------
    N = 30
    for raw_label, expected in [
        ("Thumb_Up", "confirm"),
        ("Open_Palm", "confirm"),
        ("Closed_Fist", "dismiss"),
        ("Thumb_Down", "dismiss"),
        ("Pointing_Up", "point"),
    ]:
        cases.append(
            StreamCase(
                name=f"static_held_{raw_label.lower()}",
                frames=[frame(i, raw_label, 0.9) for i in range(N)],
                expected_events=[(expected, 0, N - 1)],
                forbidden_events=_forbid_all_except(expected),
            )
        )

    # --- Static rejection cases --------------------------------------------
    # Below-threshold score — must not fire.
    cases.append(
        StreamCase(
            name="static_low_score",
            frames=[frame(i, "Thumb_Up", 0.3) for i in range(N)],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )
    # No hand visible.
    cases.append(
        StreamCase(
            name="no_hand_at_all",
            frames=[frame(i, "", 0.0, has_hand=False) for i in range(N)],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )
    # Alternating static labels — neither wins the majority vote.
    alt_labels = ["Thumb_Up", "Closed_Fist"] * 15
    cases.append(
        StreamCase(
            name="alternating_labels",
            frames=[frame(i, lab, 0.9) for i, lab in enumerate(alt_labels)],
            expected_events=[],
            forbidden_events=["point"],  # confirm/dismiss may or may not fire; allow either
            # NB: we don't forbid confirm/dismiss because whichever wins the
            # 5-of-6 vote first is "acceptable" behaviour — the real regression
            # would be `point` firing.
        )
    )
    # Brief glimpse — 2 frames of thumb_up, rest empty.
    glimpse = [frame(i, "Thumb_Up", 0.9) if i < 2 else frame(i, "", 0.0, has_hand=False) for i in range(N)]
    cases.append(
        StreamCase(
            name="brief_glimpse",
            frames=glimpse,
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- Static with noise -------------------------------------------------
    # Held thumb_up with two noise frames sprinkled — should still fire confirm.
    pattern = ["Thumb_Up"] * 3 + [""] + ["Thumb_Up"] * 3 + [""] + ["Thumb_Up"] * 22
    cases.append(
        StreamCase(
            name="noisy_thumb_up",
            frames=[
                frame(i, lab, 0.9 if lab else 0.0, has_hand=bool(lab))
                for i, lab in enumerate(pattern)
            ],
            expected_events=[("confirm", 0, N - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )

    # Unmapped label (Victory etc.) — classifier maps to NONE, must not fire.
    cases.append(
        StreamCase(
            name="victory_unmapped",
            frames=[frame(i, "Victory", 0.9) for i in range(N)],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- Motion positives --------------------------------------------------
    SWIPE_N = 16
    # Hand moves x 0.1 -> 0.925 over 16 frames (~0.055/frame), y stable.
    cases.append(
        StreamCase(
            name="swipe_right_clean",
            frames=[
                frame(i, "", 0.0, x=0.10 + 0.055 * i, y=0.50)
                for i in range(SWIPE_N)
            ],
            expected_events=[("swipe_right", 0, SWIPE_N - 1)],
            forbidden_events=["swipe_left", "confirm", "dismiss", "point"],
        )
    )
    cases.append(
        StreamCase(
            name="swipe_left_clean",
            frames=[
                frame(i, "", 0.0, x=0.90 - 0.055 * i, y=0.50)
                for i in range(SWIPE_N)
            ],
            expected_events=[("swipe_left", 0, SWIPE_N - 1)],
            forbidden_events=["swipe_right", "confirm", "dismiss", "point"],
        )
    )

    # --- Motion rejection cases -------------------------------------------
    # Slow drift below dx threshold.
    cases.append(
        StreamCase(
            name="slow_drift",
            frames=[
                frame(i, "", 0.0, x=0.40 + 0.01 * i, y=0.50)
                for i in range(SWIPE_N)
            ],
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # Diagonal — dy exceeds dy_max.
    cases.append(
        StreamCase(
            name="diagonal_fast",
            frames=[
                frame(i, "", 0.0, x=0.10 + 0.055 * i, y=0.10 + 0.055 * i)
                for i in range(SWIPE_N)
            ],
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # Vertical only (dx == 0).
    cases.append(
        StreamCase(
            name="vertical_motion",
            frames=[
                frame(i, "", 0.0, x=0.50, y=0.10 + 0.05 * i)
                for i in range(SWIPE_N)
            ],
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # Stationary hand — no swipe, no static (empty label).
    cases.append(
        StreamCase(
            name="stationary_no_label",
            frames=[frame(i, "", 0.0, x=0.50, y=0.50) for i in range(SWIPE_N)],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- Shake -------------------------------------------------------------
    # x oscillates ±0.08 around 0.5; palm stays on-frame, dx flips every frame.
    shake_xs = [0.5 + (0.08 if i % 2 == 0 else -0.08) for i in range(14)]
    cases.append(
        StreamCase(
            name="shake_dismiss",
            frames=[frame(i, "", 0.0, x=shake_xs[i], y=0.50) for i in range(len(shake_xs))],
            expected_events=[("dismiss", 4, len(shake_xs) - 1)],
            forbidden_events=["swipe_left", "swipe_right", "confirm", "point"],
        )
    )

    # --- Mixed: hand appears mid-stream then gestures ----------------------
    # 5 no-hand frames, then 25 thumb_up — expect confirm delayed by ~5 frames
    # from the moment the hand returns.
    mixed = [
        frame(i, "", 0.0, has_hand=False) if i < 5 else frame(i, "Thumb_Up", 0.9)
        for i in range(N)
    ]
    cases.append(
        StreamCase(
            name="hand_appears_then_thumbup",
            frames=mixed,
            expected_events=[("confirm", 5, N - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )

    # Released then reformed — fires once at first pose, cooldown blocks second.
    # 12 frames of thumb_up, 5 frames of no-hand, 12 frames of thumb_up again.
    double = (
        [frame(i, "Thumb_Up", 0.9) for i in range(12)]
        + [frame(i + 12, "", 0.0, has_hand=False) for i in range(5)]
        + [frame(i + 17, "Thumb_Up", 0.9) for i in range(12)]
    )
    cases.append(
        StreamCase(
            name="double_thumbup_cooldown",
            frames=double,
            expected_events=[("confirm", 0, 11)],
            # Second fire within cooldown would be a regression.
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # ============================================================================
    # HARD TIER — adversarial cases designed to expose tradeoffs
    # ============================================================================
    # These cases push on specific classifier parameters: gesture_min_score,
    # gesture_static_required, gesture_swipe_dx_threshold, gesture_swipe_dy_max,
    # gesture_swipe_required_frames, _SHAKE_MIN_FLIPS, _SHAKE_MIN_AMPLITUDE,
    # gesture_cooldown_ms. Tightening any one of them should now hurt either
    # precision or recall on this set, so the tuner has actionable signal.

    # --- 1. Landmark jitter (realistic tremor) ----------------------------
    # Held thumb_up with hand tremor. Static path ignores landmarks, so this
    # MUST still fire confirm — it's a sanity check that jitter doesn't
    # somehow leak into static gating.
    cases.append(
        StreamCase(
            name="hard_static_thumbup_jittered",
            frames=[
                frame_jittered(i, "Thumb_Up", 0.9, x=0.50, y=0.50, seed=11)
                for i in range(N)
            ],
            expected_events=[("confirm", 0, N - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )
    # Swipe with realistic tremor — small per-frame jitter on top of a clean
    # rightward sweep. Should still detect swipe_right.
    cases.append(
        StreamCase(
            name="hard_swipe_right_jittered",
            frames=[
                frame_jittered(i, "", 0.0, x=0.10 + 0.055 * i, y=0.50, seed=22)
                for i in range(SWIPE_N)
            ],
            expected_events=[("swipe_right", 0, SWIPE_N - 1)],
            forbidden_events=["swipe_left", "confirm", "dismiss", "point"],
        )
    )

    # --- 2. Same-semantic label flicker -----------------------------------
    # Thumb_Up and Open_Palm both map to "confirm". Alternating them should
    # still hit the 5-of-6 vote since both contribute to the "confirm" tally.
    flicker_labels = ["Thumb_Up", "Open_Palm"] * 15
    cases.append(
        StreamCase(
            name="hard_confirm_label_flicker",
            frames=[frame(i, lab, 0.9) for i, lab in enumerate(flicker_labels)],
            expected_events=[("confirm", 0, N - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )

    # --- 3. Score boundary (right around 0.6) -----------------------------
    # Scores hover just above 0.6 — every frame counts toward the vote, but
    # any tuner that raises min_score above 0.62 will start dropping frames.
    # Pattern: 0.61, 0.63, 0.62, 0.64, 0.60, 0.65 → all >= min_score=0.6, so
    # confirm fires at default settings.
    above_pattern = [0.61, 0.63, 0.62, 0.64, 0.60, 0.65, 0.61, 0.62, 0.63, 0.64]
    boundary_scores = (above_pattern * 4)[:N]
    cases.append(
        StreamCase(
            name="hard_score_boundary_thumbup",
            frames=[
                frame(i, "Thumb_Up", boundary_scores[i])
                for i in range(len(boundary_scores))
            ],
            expected_events=[("confirm", 0, len(boundary_scores) - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )
    # Hold most frames just below threshold — must NOT fire.
    just_below = [0.55, 0.58, 0.59, 0.57, 0.56] * 6
    cases.append(
        StreamCase(
            name="hard_score_just_below",
            frames=[
                frame(i, "Thumb_Up", just_below[i])
                for i in range(len(just_below))
            ],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- 4. Swipe edge cases ----------------------------------------------
    # 4a. Swipe at exactly the threshold: dx over lookback=5 = 0.18 exactly.
    # Classifier uses strict `>`, so this should NOT fire.
    cases.append(
        StreamCase(
            name="hard_swipe_exact_threshold",
            frames=[
                frame(i, "", 0.0, x=0.20 + 0.036 * i, y=0.50)
                for i in range(SWIPE_N)
            ],
            # 0.036 * 5 = 0.180 exactly. dx is not strictly > 0.18.
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # 4b. Swipe just over the threshold — should fire. Calibrates the boundary.
    cases.append(
        StreamCase(
            name="hard_swipe_just_over_threshold",
            frames=[
                frame(i, "", 0.0, x=0.10 + 0.038 * i, y=0.50)
                for i in range(SWIPE_N)
            ],
            # 0.038 * 5 = 0.190, just past the 0.18 line.
            expected_events=[("swipe_right", 0, SWIPE_N - 1)],
            forbidden_events=["swipe_left", "confirm", "dismiss", "point"],
        )
    )
    # 4c. Accelerating swipe — slow start, fast end. Should fire eventually.
    accel_xs = [0.10 + 0.005 * (i ** 1.7) for i in range(SWIPE_N + 4)]
    cases.append(
        StreamCase(
            name="hard_swipe_accelerating",
            frames=[
                frame(i, "", 0.0, x=accel_xs[i], y=0.50)
                for i in range(len(accel_xs))
            ],
            expected_events=[("swipe_right", 0, len(accel_xs) - 1)],
            forbidden_events=["swipe_left", "confirm", "dismiss", "point"],
        )
    )
    # 4d. Swipe with mid-stream back-jitter. Hand sweeps right, briefly
    # twitches left at frame 8, then continues right. The streak counter
    # may break and reform, so the swipe should still fire by end.
    backjit_xs = []
    for i in range(SWIPE_N + 4):
        x = 0.10 + 0.055 * i
        if 7 <= i <= 8:
            x -= 0.06  # brief leftward dip
        backjit_xs.append(x)
    cases.append(
        StreamCase(
            name="hard_swipe_with_backjitter",
            frames=[
                frame(i, "", 0.0, x=backjit_xs[i], y=0.50)
                for i in range(len(backjit_xs))
            ],
            expected_events=[("swipe_right", 0, len(backjit_xs) - 1)],
            forbidden_events=["confirm", "dismiss", "point"],
        )
    )
    # 4e. Short-range fast swipe — high per-frame velocity but only 6 frames
    # of motion total, then stationary. The streak should reach 3 quickly...
    # actually it likely DOES fire. Make it shorter: only 4 frames of motion.
    short_fast = [0.30, 0.36, 0.43, 0.50] + [0.50] * 16
    cases.append(
        StreamCase(
            name="hard_swipe_too_short",
            frames=[
                frame(i, "", 0.0, x=short_fast[i], y=0.50)
                for i in range(len(short_fast))
            ],
            # Only 4 frames of real motion. With lookback=5, dx is computed
            # over windows that mostly include the stationary phase, so dx
            # quickly drops below threshold. Should NOT fire a swipe.
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # 4f. Two slow swipes back-to-back within cooldown.
    # First swipe fires; second is within cooldown_ms=1200 → ~36 frames.
    swipe_then_swipe = (
        [frame(i, "", 0.0, x=0.10 + 0.055 * i, y=0.50) for i in range(SWIPE_N)]
        + [frame(SWIPE_N + i, "", 0.0, x=0.10 + 0.055 * i, y=0.50) for i in range(SWIPE_N)]
    )
    cases.append(
        StreamCase(
            name="hard_double_swipe_cooldown",
            frames=swipe_then_swipe,
            # Only the first swipe should fire (second is within cooldown ~36 frames).
            expected_events=[("swipe_right", 0, SWIPE_N - 1)],
            forbidden_events=["swipe_left", "confirm", "dismiss", "point"],
        )
    )

    # --- 5. Near-shakes (must NOT fire dismiss) ----------------------------
    # 5a. Three flips only — below the min 4. Should not fire.
    near_shake_3 = [0.5 + (0.08 if (i // 2) % 2 == 0 else -0.08) for i in range(8)]
    # That alternates every 2 frames; flips = 3. Pad with stationary tail.
    near_shake_3 = near_shake_3 + [0.5] * 8
    cases.append(
        StreamCase(
            name="hard_near_shake_3_flips",
            frames=[
                frame(i, "", 0.0, x=near_shake_3[i], y=0.50)
                for i in range(len(near_shake_3))
            ],
            expected_events=[],
            forbidden_events=["dismiss", "swipe_left", "swipe_right"],
        )
    )
    # 5b. Many flips but ALL sub-amplitude (<0.05). Should not fire — the
    # qualifying-flip count never reaches 4, even though the flip count does.
    near_shake_amp = [0.50, 0.53, 0.50, 0.53, 0.50, 0.53, 0.50, 0.53, 0.50, 0.53]
    # Steps all ±0.03 — flips=9 but qualifying=0. dx_threshold also unmet.
    cases.append(
        StreamCase(
            name="hard_near_shake_subamp",
            frames=[
                frame(i, "", 0.0, x=near_shake_amp[i], y=0.50)
                for i in range(len(near_shake_amp))
            ],
            expected_events=[],
            forbidden_events=["dismiss", "swipe_left", "swipe_right"],
        )
    )

    # --- 6. Simultaneous static + near-swipe wobble -----------------------
    # User holds Thumb_Up while the palm wobbles left/right at near-swipe
    # amplitude. Should fire confirm (static), not swipe.
    # dx per lookback (5 frames) of a sine should not exceed 0.18.
    sim_xs = [0.50 + 0.06 * math.sin(i * 0.5) for i in range(N)]
    cases.append(
        StreamCase(
            name="hard_static_with_palm_wobble",
            frames=[
                frame(i, "Thumb_Up", 0.9, x=sim_xs[i], y=0.50)
                for i in range(N)
            ],
            expected_events=[("confirm", 0, N - 1)],
            # Wobble amplitude 0.06 < dx_threshold 0.18 over lookback, so no swipe.
            forbidden_events=["swipe_left", "swipe_right", "dismiss", "point"],
        )
    )

    # --- 7. Hand-presence flicker (MediaPipe dropout) ---------------------
    # 7a. Single-frame dropouts: 80% present. Each dropout RESETS state.
    # Pattern: every 5th frame is a dropout. With static_window=6 and
    # static_required=5, the buffer can never accumulate 5 valid frames
    # before a reset. Expect: confirm should NOT fire.
    cases.append(
        StreamCase(
            name="hard_dropout_every_5th",
            frames=[
                frame(i, "Thumb_Up", 0.9) if i % 5 != 4
                else frame(i, "", 0.0, has_hand=False)
                for i in range(N)
            ],
            expected_events=[],  # 4 valid frames, then reset
            forbidden_events=list(_ALL_NAMES),
        )
    )
    # 7b. Bursty dropouts: 5 missing in a row, then 25 present. After the
    # burst, classifier recovers and confirm fires from the 25-frame run.
    bursty = (
        [frame(i, "", 0.0, has_hand=False) for i in range(5)]
        + [frame(5 + i, "Thumb_Up", 0.9) for i in range(25)]
    )
    cases.append(
        StreamCase(
            name="hard_bursty_dropout_recovers",
            frames=bursty,
            expected_events=[("confirm", 5, N - 1)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )
    # 7c. Single-frame dropouts farther apart: every 7th frame missing.
    # 6 valid, 1 reset. Should fire confirm because the 6-frame window
    # gets exactly 6 valid frames between dropouts.
    cases.append(
        StreamCase(
            name="hard_dropout_every_7th",
            frames=[
                frame(i, "Thumb_Up", 0.9) if i % 7 != 6
                else frame(i, "", 0.0, has_hand=False)
                for i in range(N + 5)
            ],
            expected_events=[("confirm", 0, N + 4)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )

    # --- 8. Real-world negatives -------------------------------------------
    # 8a. User scratches head — random walk in (x, y). Score irrelevant
    # because no mapped label. Must not fire any swipe/shake.
    rng_walk = random.Random(404)
    walk_xs = [0.5]
    walk_ys = [0.5]
    for _ in range(SWIPE_N + 4):
        walk_xs.append(max(0.0, min(1.0, walk_xs[-1] + (rng_walk.random() - 0.5) * 0.04)))
        walk_ys.append(max(0.0, min(1.0, walk_ys[-1] + (rng_walk.random() - 0.5) * 0.04)))
    cases.append(
        StreamCase(
            name="hard_random_walk_scratch",
            frames=[
                frame(i, "", 0.0, x=walk_xs[i], y=walk_ys[i])
                for i in range(len(walk_xs))
            ],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )
    # 8b. User reaches for mouse — diagonal sweep with significant dy.
    # Should NOT fire swipe (dy violates dy_max=0.08).
    cases.append(
        StreamCase(
            name="hard_reach_for_mouse",
            frames=[
                frame(i, "", 0.0, x=0.20 + 0.05 * i, y=0.30 + 0.04 * i)
                for i in range(SWIPE_N)
            ],
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )
    # 8c. User gestures while talking — brief Pointing_Up flash (3 frames),
    # then random labels and palm wander. Should NOT fire point.
    talk_pattern = ["Pointing_Up"] * 3 + ["Victory", "ILoveYou", "", "Victory"] * 6
    talk_pattern = talk_pattern[:N]
    cases.append(
        StreamCase(
            name="hard_gestures_while_talking",
            frames=[
                frame(i, lab, 0.7 if lab else 0.0, x=0.5 + 0.02 * math.sin(i * 0.3), y=0.5)
                for i, lab in enumerate(talk_pattern)
            ],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- 9. Cooldown edge cases -------------------------------------------
    # 9a. (See "hard_no_refire_during_hold" below — moved to spec-mismatch
    # section since current implementation re-fires after cooldown even
    # without release.)
    # 9b. Same pose fires, hand goes away long enough for cooldown to expire,
    # then pose reforms. Both fires should land.
    long_release = (
        [frame(i, "Thumb_Up", 0.9) for i in range(12)]
        + [frame(12 + i, "", 0.0, has_hand=False) for i in range(40)]  # > cooldown
        + [frame(52 + i, "Thumb_Up", 0.9) for i in range(15)]
    )
    cases.append(
        StreamCase(
            name="hard_release_then_refire",
            frames=long_release,
            expected_events=[("confirm", 0, 11), ("confirm", 52, 66)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # --- 10. Static_required boundary --------------------------------------
    # Exactly 5 frames of Thumb_Up in a 6-frame window, sandwiched by
    # unmapped/no-vote labels. With current required=5, this should fire.
    boundary_pattern = (
        ["Victory"] * 3
        + ["Thumb_Up"] * 5  # exactly 5 in any 6-window once the buffer fills
        + ["Victory"]       # 6th frame in window is non-confirm
        + ["Victory"] * 21
    )
    cases.append(
        StreamCase(
            name="hard_static_exactly_5_of_6",
            frames=[
                frame(i, lab, 0.9 if lab else 0.0)
                for i, lab in enumerate(boundary_pattern)
            ],
            expected_events=[("confirm", 0, len(boundary_pattern) - 1)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )
    # And the reverse: only 4 of 6, must NOT fire.
    sub_boundary = (
        ["Victory"] * 3
        + ["Thumb_Up"] * 4
        + ["Victory"] * 23
    )
    cases.append(
        StreamCase(
            name="hard_static_only_4_of_6",
            frames=[
                frame(i, lab, 0.9 if lab else 0.0)
                for i, lab in enumerate(sub_boundary)
            ],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # --- Bonus: shake at exact threshold ----------------------------------
    # 4 flips with all amplitudes >= 0.05 — should fire dismiss.
    shake_min_xs = [0.5, 0.55, 0.50, 0.55, 0.50, 0.55, 0.50, 0.55, 0.50]
    cases.append(
        StreamCase(
            name="hard_shake_min_amplitude",
            frames=[
                frame(i, "", 0.0, x=shake_min_xs[i], y=0.50)
                for i in range(len(shake_min_xs))
            ],
            expected_events=[("dismiss", 0, len(shake_min_xs) - 1)],
            forbidden_events=["confirm", "point", "swipe_left", "swipe_right"],
        )
    )

    # ============================================================================
    # LATENCY-CONSTRAINED CASES — narrow expected windows make latency real
    # ============================================================================
    # These cases require the classifier to fire QUICKLY. With default
    # static_required=5, latency from "hand appears" to first fire is ~4 frames.
    # If a tuner loosens static_required to 3 → faster, but breaks
    # `hard_static_only_4_of_6`. A real precision/recall/latency tradeoff.

    # Quick-confirm: thumb_up appears, must fire by frame 6 inclusive.
    cases.append(
        StreamCase(
            name="hard_quick_confirm_window",
            frames=[frame(i, "Thumb_Up", 0.9) for i in range(20)],
            # static_required=5 → first fire at frame 4. Frame 6 is generous.
            # Tightening required to 6 → fires at 5; required to 7 → never.
            expected_events=[("confirm", 0, 6)],
            forbidden_events=_forbid_all_except("confirm"),
        )
    )

    # Slow-onset confirm: classifier won't see Thumb_Up consistently for the
    # first 8 frames (alternating with NONE/Victory), then 5 strong frames.
    # Default classifier should fire by frame ~12. If a tuner increases
    # static_window to 10 to filter noise, it will miss this latency window.
    slow_onset = (
        ["Victory", "Thumb_Up", "Victory", "Thumb_Up", "Victory", "Thumb_Up", "Victory", "Thumb_Up"]
        + ["Thumb_Up"] * 10
    )
    cases.append(
        StreamCase(
            name="hard_slow_onset_confirm",
            frames=[frame(i, lab, 0.9) for i, lab in enumerate(slow_onset)],
            expected_events=[("confirm", 0, 13)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # ============================================================================
    # EXTRA NEGATIVES — ambient noise that should not produce ANY fire
    # ============================================================================
    # Tiny tremor only — 21 frames of barely-moving palm with no label.
    # Tuners that lower dx_threshold below 0.05 will start firing spurious
    # swipes here.
    rng_tremor = random.Random(909)
    tremor_xs = [0.5 + (rng_tremor.random() - 0.5) * 0.04 for _ in range(SWIPE_N + 6)]
    cases.append(
        StreamCase(
            name="hard_idle_tremor_no_label",
            frames=[
                frame(i, "", 0.0, x=tremor_xs[i], y=0.50)
                for i in range(len(tremor_xs))
            ],
            expected_events=[],
            forbidden_events=list(_ALL_NAMES),
        )
    )

    # Slow ramp that just barely doesn't reach swipe threshold — dx=0.17 over
    # the lookback window. A tuner lowering dx_threshold to 0.16 would start
    # firing spurious swipes here.
    cases.append(
        StreamCase(
            name="hard_slow_ramp_below_dx",
            frames=[
                frame(i, "", 0.0, x=0.20 + 0.034 * i, y=0.50)
                for i in range(SWIPE_N + 4)
            ],
            # 0.034 * 5 = 0.170 — strictly < 0.18. No swipe.
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )

    # Diagonal at exactly the dy_max boundary — dy = 0.08 per lookback.
    # Classifier uses strict `<` for dy, so abs(dy) < 0.08 fails when dy=0.08.
    cases.append(
        StreamCase(
            name="hard_diagonal_exact_dymax",
            frames=[
                frame(i, "", 0.0, x=0.10 + 0.055 * i, y=0.10 + 0.016 * i)
                for i in range(SWIPE_N)
            ],
            # dx*5 = 0.275 (passes), dy*5 = 0.080 (fails strict <).
            expected_events=[],
            forbidden_events=["swipe_left", "swipe_right"],
        )
    )

    # ============================================================================
    # SPEC-VS-IMPL MISMATCH CASES — these encode product-intent behaviour that
    # current code doesn't quite deliver. These are the cases where a tuner has
    # to make a real precision/recall trade.
    # ============================================================================

    # Spec: a held pose must NOT re-fire for the lifetime of the hold, even if
    # cooldown expires. Current implementation re-fires after cooldown if the
    # buffer happens to repopulate (no release detection). Mark the SECOND
    # fire as forbidden — at default settings this is an FP at frame 44.
    held_long = [frame(i, "Thumb_Up", 0.9) for i in range(60)]
    cases.append(
        StreamCase(
            name="hard_no_refire_during_hold",
            frames=held_long,
            expected_events=[("confirm", 0, 10)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
            # NB: any second `confirm` past frame 10 will count as FP via
            # the harness's "unmatched fire" rule. Tightening cooldown_ms
            # would fix this but break `hard_release_then_refire`.
        )
    )

    # Regression: direct pose switch WITHOUT releasing hand must still
    # eventually fire the new gesture, just with the design-accepted
    # latency penalty from draining the vote buffer on release (see
    # classifier.py for the Codex review round 8 tradeoff rationale).
    # User holds Thumb_Up (fire confirm), then directly forms Closed_Fist
    # (expect dismiss). Dismiss fires ~8 frames after Closed_Fist starts
    # (5-frame release-streak crossing + 5-frame fresh debounce - 2
    # overlap = 8).
    direct_switch = (
        [frame(i, "Thumb_Up", 0.9) for i in range(10)]
        + [frame(10 + i, "Closed_Fist", 0.9) for i in range(20)]
    )
    cases.append(
        StreamCase(
            name="hard_direct_pose_switch",
            frames=direct_switch,
            expected_events=[("confirm", 0, 4), ("dismiss", 10, 24)],
            forbidden_events=["point", "swipe_left", "swipe_right"],
        )
    )

    # Regression (Codex review round 7 P1): sustained cross-semantic
    # misclassification must not produce a spurious cross-semantic fire
    # when the release streak crosses threshold. User holds Thumb_Up
    # (confirm). MediaPipe misclassifies as Closed_Fist for 5 CONSECUTIVE
    # frames (matching `gesture_static_required`). Pre-fix behaviour:
    # streak crosses threshold at frame 9, lock clears, the 5 accumulated
    # dismiss votes in `_static_labels` win on the same tick, and the
    # classifier emits a REAL `dismiss` — opposite semantic, fully
    # user-visible. Fix drains the vote buffer together with the lock so
    # those stale votes don't count. User then returns to Thumb_Up;
    # because cooldown is per-name and dismiss never fired, confirm
    # stays on cooldown until frame 40 and the next Thumb_Up-dominated
    # vote would fire then — but our `expected_events` allows [0, 10]
    # only, since the real dismiss-era is past. Any cross-fire during
    # [5, 9] counts as a clear regression.
    # Test probes exactly the critical property: the 5 Closed_Fist frames
    # must NOT cause a spurious `dismiss` event around frame 9. We truncate
    # the stream there — follow-on behaviour (whether a second confirm
    # re-fires after cooldown) is a separate UX question covered by the
    # flicker / relax cases above. What Codex P1 cared about is the
    # cross-semantic leak, and that's what this case guards against.
    cross_sustained = (
        [frame(i, "Thumb_Up", 0.9) for i in range(5)]
        + [frame(5 + i, "Closed_Fist", 0.9) for i in range(5)]
        + [frame(10, "", 0.0, has_hand=False)]  # natural end-of-stream sentinel
    )
    cases.append(
        StreamCase(
            name="hard_cross_mapping_sustained",
            frames=cross_sustained,
            expected_events=[("confirm", 0, 4)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Regression (Codex review round 6 P1): cross-semantic misclassification
    # during a long hold. User holds Thumb_Up (confirm) for 60 frames;
    # MediaPipe briefly emits `Closed_Fist` (dismiss) for one frame every
    # 10 frames. Only ONE confirm may fire — the cross-mapped flicker
    # must not be treated as a release. Without the unified release-streak
    # gate, the cross-mapped frame would clear the KOBE-lock instantly
    # (different mapping -> clear), and once cooldown elapsed a second
    # confirm would fire around frame 44 (duplicate). The unified streak
    # counter treats a single cross-mapped frame the same way it treats a
    # single unmapped frame: noise, not release.
    cross_flicker = []
    for i in range(60):
        if i % 10 == 9:
            cross_flicker.append(frame(i, "Closed_Fist", 0.9))
        else:
            cross_flicker.append(frame(i, "Thumb_Up", 0.9))
    cases.append(
        StreamCase(
            name="hard_cross_mapping_flicker",
            frames=cross_flicker,
            expected_events=[("confirm", 0, 10)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Regression (Codex review round 4 P1): same-semantic raw-label flicker
    # during a long continuous hold must not re-fire. User holds confirm
    # for 60 frames; MediaPipe alternates Thumb_Up / Open_Palm every frame
    # (both map to confirm). Without the KOBE-semantic lock, the raw-label
    # alternation would clear a raw-based lock on every frame, and once
    # `gesture_cooldown_ms` (≈36 frames at 30 fps) elapsed a second
    # confirm would fire around frame 44 — a duplicate on a single held
    # intent. The KOBE-semantic lock blocks the second fire: the winner
    # stays `confirm`, the lock stays `confirm`, no release ever occurs.
    long_flicker_labels = ["Thumb_Up", "Open_Palm"] * 30
    cases.append(
        StreamCase(
            name="hard_long_same_semantic_flicker",
            frames=[frame(i, lab, 0.9) for i, lab in enumerate(long_flicker_labels)],
            expected_events=[("confirm", 0, 59)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Regression: user fires confirm, relaxes into a neutral/unmapped pose
    # while staying in frame (MediaPipe reports 'Victory'/low-score for a
    # sustained stretch), then forms Thumb_Up again to fire a SECOND
    # confirm. Both fires must land. The round-1 hold-lock fix broke this
    # by never clearing the lock on in-frame unmapped frames; round-2
    # added a `_static_unmapped_streak` counter so a sustained
    # `>=static_required` unmapped stretch clears the lock.
    #
    # Frame layout: 6 Thumb_Up (fire 1) + 6 Victory (release, sustained) +
    # 40 Victory (hold past cooldown, 46*33ms ≈ 1518ms > 1200ms cooldown) +
    # 10 Thumb_Up (fire 2, now clear to fire because lock is released AND
    # cooldown expired).
    relax_and_refire = (
        [frame(i, "Thumb_Up", 0.9) for i in range(6)]
        + [frame(6 + i, "Victory", 0.3) for i in range(46)]
        + [frame(52 + i, "Thumb_Up", 0.9) for i in range(10)]
    )
    cases.append(
        StreamCase(
            name="hard_relax_inframe_then_refire",
            frames=relax_and_refire,
            expected_events=[("confirm", 0, 11), ("confirm", 52, 61)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Regression: MediaPipe flicker during a continuous hold (single
    # unmapped-label frame every 10 frames). The user is clearly still
    # holding the same pose, so only ONE confirm must fire. Without
    # release-detection preservation (Codex review P1 fix), the flicker
    # clears the hold-lock; after the 1200 ms cooldown expires 5 further
    # good frames can trigger a second FP. This case is a canary: any
    # regression that makes the lock fragile against noise lights it up.
    flicker = []
    for i in range(60):
        if i % 10 == 9:
            # One unmapped, low-score "Victory" frame — hand present, label
            # not in _PRETRAINED_MAP, so classifier drops it into NONE_LABEL
            # via the same branch that the broken fix used to clear the lock.
            flicker.append(frame(i, "Victory", 0.4))
        else:
            flicker.append(frame(i, "Thumb_Up", 0.9))
    cases.append(
        StreamCase(
            name="hard_flicker_during_hold",
            frames=flicker,
            expected_events=[("confirm", 0, 10)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Spec: brief but unambiguous gesture (4 strong Thumb_Up frames, then
    # natural release) should fire confirm. Current implementation requires 5
    # of 6, so this never fires → FN at default settings.
    brief_intent = (
        [frame(i, "Thumb_Up", 0.95) for i in range(4)]
        + [frame(4 + i, "", 0.0, has_hand=False) for i in range(20)]
    )
    cases.append(
        StreamCase(
            name="hard_brief_but_intentional",
            frames=brief_intent,
            # Product intent: 4 confident Thumb_Up frames = confirm.
            # Default classifier requires 5/6 → FN.
            expected_events=[("confirm", 0, 6)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Spec: rapid back-and-forth swipes (left then right) within 1s should
    # fire BOTH events for navigation undo/redo. Default cooldown_ms=1200
    # blocks the second swipe even though it's a different direction
    # (cooldown is per-name, but the user might tighten cooldown trying to
    # fix this and break `hard_double_swipe_cooldown`).
    rev_swipe = (
        [frame(i, "", 0.0, x=0.10 + 0.055 * i, y=0.50) for i in range(SWIPE_N)]
        + [frame(SWIPE_N + i, "", 0.0, x=0.90 - 0.055 * i, y=0.50) for i in range(SWIPE_N)]
    )
    cases.append(
        StreamCase(
            name="hard_swipe_then_reverse",
            frames=rev_swipe,
            # Spec: both swipes recognised. Different names so cooldown OK in
            # principle. But the palm buffer is cleared after the first swipe
            # fires, then the leftward sweep takes time to re-register. Should
            # eventually fire — let's check.
            expected_events=[
                ("swipe_right", 0, SWIPE_N - 1),
                ("swipe_left", SWIPE_N, SWIPE_N + SWIPE_N - 1),
            ],
            forbidden_events=["confirm", "dismiss", "point"],
        )
    )

    # Spec: tight latency budget. After hand appears, confirm must fire
    # within 5 frames. Default needs 4 frames of Thumb_Up to fill window
    # → fires at frame 4. We require by frame 5 — passes by 1.
    # If a tuner raises gesture_static_required to 6, this becomes FN.
    tight_latency = [frame(i, "Thumb_Up", 0.95) for i in range(20)]
    cases.append(
        StreamCase(
            name="hard_tight_latency_budget",
            frames=tight_latency,
            expected_events=[("confirm", 0, 5)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    # Spec: low-confidence sustained gesture (score 0.55, just below default
    # threshold) should fire if held long enough. Current implementation
    # rejects everything below min_score → FN. A tuner that lowers
    # min_score to 0.5 will pass this but start firing on noise (see
    # `static_low_score` and `hard_score_just_below`).
    low_conf_held = [frame(i, "Thumb_Up", 0.55) for i in range(N)]
    cases.append(
        StreamCase(
            name="hard_low_conf_sustained",
            frames=low_conf_held,
            expected_events=[("confirm", 0, N - 1)],
            forbidden_events=["dismiss", "point", "swipe_left", "swipe_right"],
        )
    )

    return cases


# --- Dataset split (so optimizer can't overfit without noticing) -----------
# These are name prefixes; any case whose name startswith one of these goes in
# the held-out eval split. Tuners should watch `score` on the union, but the
# more conservative "don't regress held-out" rule is enforced by the harness.
#
# Roughly 20% of hard-tier cases are held out — chosen to span jitter, score
# boundary, swipe edges, dropout recovery, and cooldown-edge behaviours so a
# tuner that only chases train metrics will visibly degrade on heldout.
HELDOUT_PREFIXES: tuple[str, ...] = (
    # easy tier
    "swipe_left_clean",
    "static_held_pointing_up",
    "noisy_thumb_up",
    "shake_dismiss",
    # hard tier (~20% — span jitter, score, swipe edge, dropout, cooldown,
    # AND at least one current-implementation failure so the heldout split
    # also exposes regressions when the tuner fixes one and breaks another).
    "hard_static_thumbup_jittered",
    "hard_score_just_below",
    "hard_swipe_just_over_threshold",
    "hard_bursty_dropout_recovers",
    "hard_release_then_refire",
    "hard_static_exactly_5_of_6",
    "hard_brief_but_intentional",
    "hard_no_refire_during_hold",
)


def split_cases() -> tuple[list[StreamCase], list[StreamCase]]:
    all_cases = make_cases()
    train = [c for c in all_cases if not any(c.name.startswith(p) for p in HELDOUT_PREFIXES)]
    heldout = [c for c in all_cases if any(c.name.startswith(p) for p in HELDOUT_PREFIXES)]
    return train, heldout


if __name__ == "__main__":
    train, heldout = split_cases()
    print(f"Train cases ({len(train)}):")
    for c in train:
        print(f"  {c.name:32s}  frames={len(c.frames):3d}  expected={c.expected_events}")
    print(f"\nHeld-out cases ({len(heldout)}):")
    for c in heldout:
        print(f"  {c.name:32s}  frames={len(c.frames):3d}  expected={c.expected_events}")
