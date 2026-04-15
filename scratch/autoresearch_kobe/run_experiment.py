"""One experiment: eval current git state, append a row to results.tsv.

Usage:
    uv run python scratch/autoresearch_kobe/run_experiment.py "<description>"

The description is stored verbatim in the TSV alongside the short commit SHA,
train/heldout/combined F1 + latency + score, and a placeholder status column.
The keep/discard decision is made by the iteration loop (the caller) based on
`score` vs the current best; this script just logs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Make sibling modules importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).parent))

# `harness.evaluate()` without explicit Settings uses `_pristine_settings()`
# which bypasses env_file AND env var resolution — so no pre-import env
# massage is needed. See harness.py module docstring for the rationale.
from harness import evaluate, format_report  # noqa: E402


def _git_short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        ).strip()
    except Exception:
        return "nosha"


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        return bool(out.strip())
    except Exception:
        return False


def main() -> int:
    description = sys.argv[1] if len(sys.argv) > 1 else "<unspecified>"
    sha = _git_short_sha()
    if _git_dirty():
        sha = f"{sha}-dirty"

    tsv = Path(__file__).parent / "results.tsv"
    header = (
        "commit\ttrain_f1\theldout_f1\tcombined_f1\t"
        "precision\trecall\tlatency\tscore\tstatus\tdescription\n"
    )
    if not tsv.exists():
        tsv.write_text(header, encoding="utf-8")

    # TSV requires tab- and newline-free fields. Any copy-pasted
    # description containing either would shift columns or split the row
    # in half, making `results.tsv` unparseable. Collapse both to spaces.
    safe_description = description.replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()

    # Run the eval in a try block so a classifier regression (import error,
    # unhandled exception inside `evaluate()`, etc.) gets logged as a
    # `crash` row per program.md, not swallowed. The tuning loop needs to
    # SEE failed experiments — silent aborts are the worst-case scenario
    # because a broken change appears identical in `results.tsv` to
    # "experiment never ran".
    try:
        ev = evaluate()
        print(format_report(ev))
    except Exception as e:
        err_summary = str(e).replace("\t", " ").replace("\n", " ").replace("\r", " ").strip()[:200]
        row = (
            f"{sha}\t0.0000\t0.0000\t0.0000\t"
            f"0.0000\t0.0000\t0.00\t0.0000\t"
            f"crash\t{safe_description} | crash: {err_summary}\n"
        )
        with tsv.open("a", encoding="utf-8") as fh:
            fh.write(row)
        print(f"\nExperiment CRASHED — row appended to {tsv}:")
        print(row.rstrip())
        return 1

    train_f1 = ev["train"]["f1"]
    heldout_f1 = ev["heldout"]["f1"]
    combined = ev["combined"]
    row = (
        f"{sha}\t{train_f1:.4f}\t{heldout_f1:.4f}\t{combined['f1']:.4f}\t"
        f"{combined['precision']:.4f}\t{combined['recall']:.4f}\t"
        f"{combined['avg_latency_frames']:.2f}\t{combined['score']:.4f}\t"
        f"pending\t{safe_description}\n"
    )
    with tsv.open("a", encoding="utf-8") as fh:
        fh.write(row)

    print(f"\nRow appended to {tsv}:")
    print(row.rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
