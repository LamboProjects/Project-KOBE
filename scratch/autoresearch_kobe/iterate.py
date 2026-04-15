"""Iteration helper for the gesture tuning loop.

Not part of the canonical autoresearch protocol (per `program.md` the protocol
is: edit → commit → eval → keep/revert). This utility lets me sweep one or
more parameters in-process WITHOUT committing each variant, so I can converge
on a promising region first, then do real commits for the winners.

Usage:
    uv run python scratch/autoresearch_kobe/iterate.py \
        --param gesture_static_required --values 3,4,5,6

    uv run python scratch/autoresearch_kobe/iterate.py --grid \
        --param gesture_static_required --values 4,5 \
        --param gesture_static_window --values 5,6,7

The script instantiates `Settings` with env overrides (via `**overrides` to the
constructor — pydantic-settings honors kwargs) and runs the full harness for
each combination. Prints a ranked table. Never writes to `results.tsv` — that's
reserved for committed experiments.
"""
from __future__ import annotations

# CRITICAL: set `KOBE_ENV_FILE` BEFORE importing anything that touches
# `kobe.config`. See run_experiment.py for the full explanation — in short,
# `Settings.model_config.env_file` freezes at class definition time, so a
# late override is a no-op and the sweep would benchmark against a local
# `config/.env` instead of pristine defaults.
import os as _os_preload

_NULL_PATH = "NUL" if _os_preload.name == "nt" else "/dev/null"
_os_preload.environ["KOBE_ENV_FILE"] = _NULL_PATH

import argparse
import itertools
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# These imports trigger `kobe.config.Settings` class definition which
# resolves `env_file` via `_resolve_env_file()`; the env override above
# must be in place first.
from kobe.config import Settings  # noqa: E402

from harness import evaluate  # noqa: E402


def _parse_value(raw: str) -> float | int | str | bool:
    r = raw.strip()
    if r.lower() in ("true", "false"):
        return r.lower() == "true"
    try:
        return int(r)
    except ValueError:
        pass
    try:
        return float(r)
    except ValueError:
        pass
    return r


def _values(s: str) -> list[object]:
    return [_parse_value(v) for v in s.split(",")]


def run_one(overrides: dict[str, object]) -> dict[str, float]:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    ev = evaluate(settings)
    m = ev["combined"]
    return {
        "f1": m["f1"],
        "precision": m["precision"],
        "recall": m["recall"],
        "latency": m["avg_latency_frames"],
        "score": m["score"],
        "train_f1": ev["train"]["f1"],
        "heldout_f1": ev["heldout"]["f1"],
    }


def main() -> int:
    # Reaffirm the override for clarity; the critical assignment happens at
    # module-top so the early `kobe.config` import sees the pristine path.
    assert os.environ.get("KOBE_ENV_FILE") == _NULL_PATH

    ap = argparse.ArgumentParser()
    ap.add_argument("--param", action="append", required=True, help="Param name, repeatable")
    ap.add_argument("--values", action="append", required=True, help="Comma-separated values, one --values per --param")
    ap.add_argument("--grid", action="store_true", help="Cartesian product (default: zip by index)")
    args = ap.parse_args()

    if len(args.param) != len(args.values):
        print("Error: --param and --values count must match", file=sys.stderr)
        return 2

    param_names: list[str] = args.param
    value_lists: list[list[object]] = [_values(v) for v in args.values]

    baseline = run_one({})
    rows: list[tuple[dict[str, object], dict[str, float]]] = [({}, baseline)]

    combos: list[tuple[object, ...]]
    if args.grid:
        combos = list(itertools.product(*value_lists))
    else:
        max_len = max(len(vs) for vs in value_lists)
        combos = [tuple(vs[i] if i < len(vs) else vs[-1] for vs in value_lists) for i in range(max_len)]

    for combo in combos:
        override = dict(zip(param_names, combo))
        result = run_one(override)
        rows.append((override, result))

    # Rank by score.
    rows.sort(key=lambda r: -r[1]["score"])
    base_score = baseline["score"]

    print()
    print(f"{'rank':<5}{'overrides':<48}{'F1':<10}{'P':<10}{'R':<10}{'lat':<8}{'score':<10}{'delta':<10}")
    print("-" * 120)
    for i, (override, result) in enumerate(rows, start=1):
        ov = ", ".join(f"{k}={v}" for k, v in override.items()) if override else "(baseline)"
        delta = result["score"] - base_score
        print(
            f"{i:<5}{ov:<48}"
            f"{result['f1']:<10.4f}{result['precision']:<10.4f}{result['recall']:<10.4f}"
            f"{result['latency']:<8.2f}{result['score']:<10.4f}{delta:+.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
