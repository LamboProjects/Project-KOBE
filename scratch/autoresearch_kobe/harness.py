"""Evaluation harness for the gesture classifier.

Runs the classifier deterministically against a fixed synthetic dataset,
matches emitted events against ground-truth windows, and returns
precision/recall/F1/mean-latency.

Matching rules:
  - Expected events are matched in order: the first unmatched fire with the
    same name that lands inside the window wins.
  - Unmatched fires are counted as false positives (whether the name was in
    `forbidden_events` or the fire was outside the expected window).
  - Missed expecteds are false negatives.
  - Latency is tracked only for TPs (fire_frame - window_min).

Score formula:
  score = f1 - 0.005 * mean_latency_frames
so F1 strictly dominates but latency breaks ties.

Determinism: `_pristine_settings()` constructs a fresh `Settings` with
`_env_file=None, _env_prefix="NEVER_MATCH_"`, which bypasses both the
class-frozen `env_file` path AND all `GESTURE_*`/other env var resolution.
So the harness runs against the class defaults regardless of what the
caller's `config/.env` or shell env say, and importing this module has no
side effects on `os.environ` or `kobe.config.Settings`.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from kobe.config import Settings
from kobe.gestures.classifier import GestureClassifier

from synth import StreamCase, make_cases, split_cases


def _pristine_settings(**overrides: object) -> Settings:
    """Build a `Settings` instance that ignores all env files and env vars.

    Pydantic-settings resolves configuration in this order: kwargs > env
    vars > env file > class defaults. `_env_file=None` disables the env
    file lookup (overriding whatever `_resolve_env_file()` baked in at
    class-definition time). `_env_prefix="NEVER_MATCH_"` re-points the env
    var lookup at a prefix that no real variable uses, which effectively
    turns off env var resolution too. The resulting instance reflects only
    the Python class defaults plus the caller's explicit `overrides`.
    """
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        _env_prefix="NEVER_MATCH_",  # type: ignore[call-arg]
        **overrides,
    )


@dataclass
class StreamResult:
    name: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    latencies: list[int] = field(default_factory=list)
    fires: list[tuple[int, str]] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)


def run_stream(case: StreamCase, settings: Settings) -> StreamResult:
    """Run one stream through a fresh classifier and score it."""
    classifier = GestureClassifier(settings)
    classifier.reset()

    fires: list[tuple[int, str]] = []
    for i, fr in enumerate(case.frames):
        for ev in classifier.push(fr):
            fires.append((i, ev.name))

    result = StreamResult(name=case.name, fires=fires)
    matched = [False] * len(fires)

    for exp_name, min_f, max_f in case.expected_events:
        hit_idx: int | None = None
        for j, (fire_idx, fire_name) in enumerate(fires):
            if matched[j]:
                continue
            if fire_name == exp_name and min_f <= fire_idx <= max_f:
                hit_idx = j
                break
        if hit_idx is not None:
            result.tp += 1
            matched[hit_idx] = True
            result.latencies.append(fires[hit_idx][0] - min_f)
        else:
            result.fn += 1

    for j, (fire_idx, fire_name) in enumerate(fires):
        if matched[j]:
            continue
        result.fp += 1
        if fire_name in case.forbidden_events:
            result.forbidden_hits.append(fire_name)

    return result


def aggregate(results: list[StreamResult]) -> dict[str, Any]:
    tp = sum(r.tp for r in results)
    fp = sum(r.fp for r in results)
    fn = sum(r.fn for r in results)
    all_latencies = [latency for r in results for latency in r.latencies]
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    avg_latency = statistics.mean(all_latencies) if all_latencies else 0.0
    score = f1 - 0.005 * avg_latency
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "avg_latency_frames": avg_latency,
        "score": score,
    }


def evaluate(settings: Settings | None = None) -> dict[str, Any]:
    """Run the full dataset (train+held-out) and return per-split + combined metrics.

    Returns dict with keys: `train`, `heldout`, `combined`, each a metrics dict.
    Also includes `per_stream` with the raw StreamResult list for debugging.

    If `settings` is omitted, `_pristine_settings()` is used so the harness
    is deterministic regardless of the caller's environment.
    """
    settings = settings or _pristine_settings()
    train_cases, heldout_cases = split_cases()
    train_results = [run_stream(c, settings) for c in train_cases]
    heldout_results = [run_stream(c, settings) for c in heldout_cases]
    return {
        "train": aggregate(train_results),
        "heldout": aggregate(heldout_results),
        "combined": aggregate(train_results + heldout_results),
        "per_stream": train_results + heldout_results,
    }


def format_report(evaluation: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("Per-stream results:")
    for r in evaluation["per_stream"]:
        fires_s = ", ".join(f"{i}:{n}" for i, n in r.fires) or "-"
        out.append(
            f"  {r.name:32s}  tp={r.tp} fp={r.fp} fn={r.fn}  "
            f"lat={r.latencies or '-'}  fires=[{fires_s}]"
        )
    for split in ("train", "heldout", "combined"):
        m = evaluation[split]
        out.append(
            f"\n[{split}]  tp={m['tp']} fp={m['fp']} fn={m['fn']}  "
            f"P={m['precision']:.4f}  R={m['recall']:.4f}  "
            f"F1={m['f1']:.4f}  lat={m['avg_latency_frames']:.2f}  "
            f"score={m['score']:.4f}"
        )
    return "\n".join(out)


if __name__ == "__main__":
    print(format_report(evaluate()))
