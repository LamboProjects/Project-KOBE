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

    return cases


# --- Dataset split (so optimizer can't overfit without noticing) -----------
# These are name prefixes; any case whose name startswith one of these goes in
# the held-out eval split. Tuners should watch `score` on the union, but the
# more conservative "don't regress held-out" rule is enforced by the harness.
HELDOUT_PREFIXES: tuple[str, ...] = (
    "swipe_left_clean",
    "static_held_pointing_up",
    "noisy_thumb_up",
    "shake_dismiss",
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
