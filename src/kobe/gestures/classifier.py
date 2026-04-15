"""Pure-Python gesture classifier for Project KOBE Phase 5.

Consumes `FrameResult` snapshots from the camera worker and emits
KOBE-semantic `GestureEvent` values. Two tracks run over a sliding window:
static gestures (debounced MediaPipe label, remapped to confirm/dismiss/
point) and motion gestures (swipe_left/swipe_right/shake-as-dismiss from
landmark 9 travel). Pure transformer: no I/O, no threads, no globals
beyond the pretrained lookup. `push()` may return 0, 1, or (rarely) 2
events per frame.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Deque

import structlog

from kobe.config import Settings

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from kobe.gestures.camera import FrameResult


log = structlog.get_logger(__name__)


# MediaPipe pretrained label -> KOBE semantic name. Labels absent from this
# map (Victory, ILoveYou, None, ...) deliberately produce no static event.
_PRETRAINED_MAP: dict[str, str] = {
    "Thumb_Up": "confirm",
    "Open_Palm": "confirm",
    "Closed_Fist": "dismiss",
    "Thumb_Down": "dismiss",
    "Pointing_Up": "point",
}

_NONE_LABEL = "none"           # sentinel for "no usable KOBE label this frame"
_PALM_LANDMARK = 9             # middle-finger MCP = stable palm centroid proxy
_SHAKE_MIN_FLIPS = 4
_SHAKE_MIN_AMPLITUDE = 0.05


@dataclass(frozen=True)
class GestureEvent:
    """Internal classifier output. The service wraps this into a bus event."""

    name: str           # "swipe_left" | "swipe_right" | "point" | "confirm" | "dismiss"
    confidence: float
    hand: str           # "left" | "right" | "unknown"
    raw_label: str      # e.g. "Thumb_Up", "swipe", "shake"
    timestamp_ms: int   # mirrors FrameResult.timestamp_ms


class GestureClassifier:
    """Sliding-window gesture detector.

    State: three parallel deques for the static vote (labels/scores/hands);
    one `_palm_buffer` of landmark-9 samples for motion; a
    `(_swipe_streak_dir, _swipe_streak_count)` pair for consecutive-frame
    direction voting; and `_last_fire_ms` as a per-KOBE-name cooldown
    ledger (shake + static dismiss share the 'dismiss' bucket).
    """

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        sw = max(1, int(settings.gesture_static_window))
        mw = max(1, int(settings.gesture_swipe_window))
        self._static_labels: Deque[str] = deque(maxlen=sw)
        self._static_scores: Deque[float] = deque(maxlen=sw)
        self._static_hands: Deque[str] = deque(maxlen=sw)
        # Parallel deque of the actual MediaPipe labels so debug/telemetry
        # (GestureEvent.raw_label) reflects the true source label rather than
        # a canonical reconstruction.
        self._static_raw_labels: Deque[str] = deque(maxlen=sw)
        self._palm_buffer: Deque[tuple[float, float, int]] = deque(maxlen=mw)
        self._swipe_streak_dir: str | None = None
        self._swipe_streak_count: int = 0
        self._last_fire_ms: dict[str, int] = {}
        # Release-detection guard: after a static fires, record the KOBE
        # semantic name so a continuously-held intent can't re-fire the
        # moment the cooldown expires. We key on KOBE name (`confirm` /
        # `dismiss` / `point`) rather than raw MediaPipe label because:
        #   • Same-semantic label flicker (Thumb_Up ↔ Open_Palm, both
        #     confirm) during a single held gesture looks identical to a
        #     deliberate same-semantic switch — if the lock cleared on raw
        #     change, MediaPipe flicker on long holds would re-fire once
        #     the cooldown elapsed (Codex review round 4 P1).
        #   • Same-semantic re-intent is ambiguous UX: if the user wants
        #     two confirms, they can release the hand (no-hand reset) or
        #     hold a neutral/unmapped pose for `gesture_static_required`
        #     frames (sustained release, see below).
        #
        # Cleared on:
        #   (a) no-hand frame — hand physically left the view,
        #   (b) valid-label frame with a *different KOBE mapping* — user
        #       switched to a different semantic action (confirm→dismiss),
        #   (c) `_static_unmapped_streak` consecutive frames with no usable
        #       KOBE label — user relaxed into a neutral/unmapped pose
        #       while still in frame. Gated by `gesture_static_required`
        #       so a single MediaPipe flicker doesn't count as release,
        #       but a sustained relaxation does.
        self._static_hold_lock: str | None = None
        # Counts consecutive unmapped-or-low-score frames while a hold lock
        # is armed. Reset to 0 on any mapped high-confidence frame or
        # explicit release path. Used to distinguish transient flicker from
        # genuine in-frame relaxation.
        self._static_unmapped_streak: int = 0

    # ------------------------------------------------------------------ API

    def reset(self) -> None:
        """Drop all sliding-window state. Cooldowns are cleared too."""
        self._static_labels.clear()
        self._static_scores.clear()
        self._static_hands.clear()
        self._static_raw_labels.clear()
        self._palm_buffer.clear()
        self._swipe_streak_dir = None
        self._swipe_streak_count = 0
        self._last_fire_ms.clear()
        self._static_hold_lock = None
        self._static_unmapped_streak = 0

    def push(self, frame: "FrameResult") -> list[GestureEvent]:
        """Append a frame and return any gestures that fire on this tick.

        May return zero, one, or (rarely) two events — e.g. a swipe motion
        completing on the same frame that a held static label crosses its
        debounce threshold.
        """
        events: list[GestureEvent] = []
        has_hand = bool(frame.landmarks) and len(frame.landmarks) >= 21

        if not has_hand:
            # A no-hand frame must reset the static + motion machinery FIRST,
            # before any fire check. Otherwise an existing 5-of-6 vote from
            # the previous frames would still trigger a static fire on the
            # exact frame the hand disappears, creating a spurious
            # confirm/dismiss/point right at tracking dropout.
            self._swipe_streak_dir = None
            self._swipe_streak_count = 0
            self._palm_buffer.clear()
            self._static_labels.clear()
            self._static_scores.clear()
            self._static_hands.clear()
            self._static_raw_labels.clear()
            # No-hand counts as release — drop the hold-lock so the next
            # formed pose can fire once cooldown expires.
            self._static_hold_lock = None
            self._static_unmapped_streak = 0
            return events

        self._ingest_static(frame, has_hand)
        static_event = self._maybe_fire_static(frame.timestamp_ms)
        if static_event is not None:
            events.append(static_event)

        self._ingest_palm(frame)
        motion_event = self._maybe_fire_motion(frame)
        if motion_event is not None:
            events.append(motion_event)

        return events

    # -------------------------------------------------------------- static

    def _ingest_static(self, frame: "FrameResult", has_hand: bool) -> None:
        score = float(frame.gesture_score or 0.0)
        raw = frame.gesture_label or ""
        kobe_label = _PRETRAINED_MAP.get(raw) if raw else None
        if (
            not has_hand
            or kobe_label is None
            or score < float(self._s.gesture_min_score)
        ):
            self._static_labels.append(_NONE_LABEL)
            self._static_scores.append(0.0)
            self._static_hands.append("")
            self._static_raw_labels.append("")
            # Count this as a potential release frame — but only commit to
            # clearing the lock after `gesture_static_required` consecutive
            # unmapped/low-score frames. One-frame flicker leaves the lock
            # intact; sustained in-frame relaxation clears it so the user's
            # next deliberate pose can fire normally.
            if self._static_hold_lock is not None:
                self._static_unmapped_streak += 1
                if self._static_unmapped_streak >= int(self._s.gesture_static_required):
                    self._static_hold_lock = None
                    self._static_unmapped_streak = 0
            return
        self._static_labels.append(kobe_label)
        self._static_scores.append(score)
        hand = (frame.handedness or "").lower()
        self._static_hands.append(hand if hand in ("left", "right") else "")
        self._static_raw_labels.append(raw)
        # A mapped high-confidence frame breaks any running unmapped streak:
        # the user is back to a recognized pose.
        self._static_unmapped_streak = 0
        # Release-detection: a valid frame whose KOBE mapping differs from
        # the held-locked name means the user switched to a different
        # semantic action (e.g. confirm → dismiss). Clear the lock so the
        # new intent's vote fires normally. Same-semantic raw switches
        # (Thumb_Up ↔ Open_Palm both → confirm) do NOT clear — see the
        # _static_hold_lock rationale for why.
        if self._static_hold_lock is not None and kobe_label != self._static_hold_lock:
            self._static_hold_lock = None

    def _maybe_fire_static(self, ts_ms: int) -> GestureEvent | None:
        required = int(self._s.gesture_static_required)
        if len(self._static_labels) < required:
            return None
        counts: dict[str, int] = {}
        for label in self._static_labels:
            if label != _NONE_LABEL:
                counts[label] = counts.get(label, 0) + 1
        winner = next((n for n, c in counts.items() if c >= required), None)
        if winner is None:
            return None
        if winner == self._static_hold_lock:
            # User is still holding the same *semantic intent* that last
            # fired (same KOBE name, even if the raw MediaPipe label
            # flickers between same-semantic aliases like Thumb_Up ↔
            # Open_Palm). Drain the window so the vote doesn't keep
            # computing the same winner every frame, but do NOT emit —
            # release (hand gone, different KOBE mapping, or sustained
            # unmapped) must precede re-fire.
            self._static_labels.clear()
            self._static_scores.clear()
            self._static_hands.clear()
            self._static_raw_labels.clear()
            return None
        if self._is_on_cooldown(winner, ts_ms):
            # Cooldown still running (user released and re-formed too fast).
            # Clear the window so we don't burn CPU re-computing the same
            # winner; the next fresh buffer fills after cooldown expires.
            self._static_labels.clear()
            self._static_scores.clear()
            self._static_hands.clear()
            self._static_raw_labels.clear()
            return None
        scores = [s for lbl, s in zip(self._static_labels, self._static_scores) if lbl == winner]
        hands = [h for lbl, h in zip(self._static_labels, self._static_hands) if lbl == winner and h]
        raw_counter = Counter(
            r
            for lbl, r in zip(self._static_labels, self._static_raw_labels)
            if lbl == winner and r
        )
        most_common = raw_counter.most_common(1)
        raw_label = most_common[0][0] if most_common else _lookup_raw_label(winner)
        confidence = sum(scores) / len(scores) if scores else 0.0
        frame_count = len(scores)
        # Clear the static window so a held pose can't re-fire the moment the
        # cooldown expires — the user must release and re-form the gesture.
        # Mirrors the swipe/shake paths which clear `_palm_buffer` after firing.
        self._static_labels.clear()
        self._static_scores.clear()
        self._static_hands.clear()
        self._static_raw_labels.clear()
        # Arm the hold-lock on the KOBE semantic name. Switching to a
        # different KOBE mapping, releasing the hand, or holding a
        # sustained unmapped pose clears the lock; see `_ingest_static`.
        self._static_hold_lock = winner
        return self._emit(
            winner,
            confidence,
            _dominant_hand(hands),
            raw_label,
            int(ts_ms),
            frame_count,
        )

    # -------------------------------------------------------------- motion

    def _ingest_palm(self, frame: "FrameResult") -> None:
        try:
            x, y, _ = frame.landmarks[_PALM_LANDMARK]
        except (IndexError, ValueError):
            return
        self._palm_buffer.append((float(x), float(y), int(frame.timestamp_ms)))

    def _maybe_fire_motion(self, frame: "FrameResult") -> GestureEvent | None:
        lookback = int(self._s.gesture_swipe_lookback)
        if len(self._palm_buffer) < lookback + 1:
            return None

        x_now, y_now, _ = self._palm_buffer[-1]
        x_ref, y_ref, _ = self._palm_buffer[-1 - lookback]
        dx = x_now - x_ref
        dy = y_now - y_ref

        dx_thresh = float(self._s.gesture_swipe_dx_threshold)
        dy_max = float(self._s.gesture_swipe_dy_max)
        required = int(self._s.gesture_swipe_required_frames)

        direction: str | None = None
        if abs(dx) > dx_thresh and abs(dy) < dy_max:
            direction = "right" if dx > 0 else "left"

        if direction is None:
            self._swipe_streak_dir = None
            self._swipe_streak_count = 0
        elif direction == self._swipe_streak_dir:
            self._swipe_streak_count += 1
        else:
            self._swipe_streak_dir = direction
            self._swipe_streak_count = 1

        # Shake first — a jittery oscillation becomes dismiss rather than a
        # spurious one-direction swipe. If shake conditions are met but
        # cooldown blocks the emit, we MUST still suppress the swipe path —
        # otherwise the same oscillating samples would fall through and emit
        # a spurious swipe_left/swipe_right when the user clearly meant
        # "dismiss again".
        shake_event = self._maybe_fire_shake(frame)
        if shake_event is not None:
            return shake_event
        if self._shake_qualifies():
            # Cooldown-blocked shake. Reset streak so a later swipe still
            # works once tracking settles.
            self._swipe_streak_dir = None
            self._swipe_streak_count = 0
            return None

        if (
            self._swipe_streak_dir is None
            or self._swipe_streak_count < required
        ):
            return None

        name = "swipe_left" if self._swipe_streak_dir == "left" else "swipe_right"
        ts_ms = int(frame.timestamp_ms)
        streak_len = self._swipe_streak_count
        # Reset motion state regardless of cooldown outcome.
        self._swipe_streak_dir = None
        self._swipe_streak_count = 0
        self._palm_buffer.clear()
        if self._is_on_cooldown(name, ts_ms):
            return None
        confidence = min(1.0, abs(dx) / (2.0 * dx_thresh)) if dx_thresh else 1.0
        return self._emit(name, confidence, _frame_hand(frame), "swipe", ts_ms, streak_len)

    def _shake_qualifies(self) -> bool:
        """True if the current palm buffer satisfies shake conditions, regardless
        of cooldown. Used by `_maybe_fire_motion` to also suppress swipe output
        when a shake is in flight but cooldown-blocked — otherwise the same
        oscillating samples would fall through to the swipe path and emit a
        spurious swipe_left/swipe_right."""
        if len(self._palm_buffer) < 3:
            return False
        xs = [p[0] for p in self._palm_buffer]
        dxs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        flips = 0
        qualifying = 0
        prev_sign = 0
        for step in dxs:
            sign = 1 if step > 0 else (-1 if step < 0 else 0)
            if sign != 0 and prev_sign != 0 and sign != prev_sign:
                flips += 1
                if abs(step) > _SHAKE_MIN_AMPLITUDE:
                    qualifying += 1
            if sign != 0:
                prev_sign = sign
        return flips >= _SHAKE_MIN_FLIPS and qualifying >= _SHAKE_MIN_FLIPS

    def _maybe_fire_shake(self, frame: "FrameResult") -> GestureEvent | None:
        if not self._shake_qualifies():
            return None
        # Recompute flips for the confidence value (cheap, ~10 samples).
        xs = [p[0] for p in self._palm_buffer]
        dxs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        flips = 0
        prev_sign = 0
        for step in dxs:
            sign = 1 if step > 0 else (-1 if step < 0 else 0)
            if sign != 0 and prev_sign != 0 and sign != prev_sign:
                flips += 1
            if sign != 0:
                prev_sign = sign

        ts_ms = int(frame.timestamp_ms)
        if self._is_on_cooldown("dismiss", ts_ms):
            return None
        confidence = min(1.0, flips / (2.0 * _SHAKE_MIN_FLIPS))
        # Clear motion state so we don't fire a swipe off the tail of the shake.
        self._swipe_streak_dir = None
        self._swipe_streak_count = 0
        self._palm_buffer.clear()
        return self._emit("dismiss", confidence, _frame_hand(frame), "shake", ts_ms, len(dxs))

    # ----------------------------------------------------------- emit / cd

    def _emit(
        self,
        name: str,
        confidence: float,
        hand: str,
        raw_label: str,
        ts_ms: int,
        frame_count: int,
    ) -> GestureEvent:
        self._last_fire_ms[name] = int(ts_ms)
        event = GestureEvent(
            name=name,
            confidence=float(confidence),
            hand=hand,
            raw_label=raw_label,
            timestamp_ms=int(ts_ms),
        )
        log.info(
            "gesture_classifier_fired",
            name=event.name,
            confidence=round(event.confidence, 3),
            raw_label=event.raw_label,
            hand=event.hand,
            frame_count_in_window=frame_count,
        )
        return event

    def _is_on_cooldown(self, name: str, ts_ms: int) -> bool:
        last = self._last_fire_ms.get(name)
        return last is not None and (ts_ms - last) < int(self._s.gesture_cooldown_ms)


# ---------------------------------------------------------------- helpers


def _dominant_hand(hands: list[str]) -> str:
    """Return 'left'/'right' if a clear majority exists, else 'unknown'."""
    if not hands:
        return "unknown"
    lefts = sum(1 for h in hands if h == "left")
    rights = sum(1 for h in hands if h == "right")
    if lefts > rights:
        return "left"
    if rights > lefts:
        return "right"
    return "unknown"


def _frame_hand(frame: "FrameResult") -> str:
    hand = (frame.handedness or "").lower()
    return hand if hand in ("left", "right") else "unknown"


def _lookup_raw_label(kobe_name: str) -> str:
    """Pick a representative MediaPipe label for a KOBE name. The static
    buffer only stores KOBE labels, so we recover one canonical source
    label from the pretrained map for reporting."""
    for raw, kobe in _PRETRAINED_MAP.items():
        if kobe == kobe_name:
            return raw
    return kobe_name
