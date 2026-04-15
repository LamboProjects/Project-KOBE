# KOBE autoresearch — gesture classifier tuning

Adapts Karpathy's autoresearch loop to Project KOBE. The target is
`src/kobe/gestures/classifier.py` (pure Python, no hardware) plus the
`gesture_*` defaults in `src/kobe/config.py`. Each experiment runs a deterministic
synthetic benchmark and scores the classifier on F1 minus a small latency
penalty.

## The loop

1. Branch: `autoresearch/gesture-tuning` (already created off main).
2. Baseline: `uv run python scratch/autoresearch_kobe/run_experiment.py "baseline"` — should be the first row in `results.tsv`.
3. Iterate:
   - Pick one change (config default adjustment, or small code tweak in classifier.py).
   - `git commit` with a short message describing the change.
   - `uv run python scratch/autoresearch_kobe/run_experiment.py "<description>"`.
   - The script appends a row to `results.tsv`:
     `<sha>\t<f1>\t<precision>\t<recall>\t<latency_frames>\t<score>\t<keep|discard|crash>\t<description>`
   - If `score` is strictly higher than the current branch tip's best → keep, advance.
   - Otherwise `git reset --hard HEAD~1` to revert.
4. Repeat until marginal gains are in the noise floor.

## What "score" means

- `precision = TP / (TP + FP)` — did every fire correspond to an expected gesture in its expected window?
- `recall = TP / (TP + FN)` — did every expected gesture in fact fire?
- `f1 = 2PR / (P + R)`.
- `latency_frames` = mean frames from window start to the frame the classifier fired (tracked only for TPs).
- `score = f1 - 0.005 * latency_frames` — F1 dominates; latency is a tiebreak.

FP penalties are higher than FN penalties in the synthetic dataset (people hate
accidental dismissals more than silent misses), but this is expressed via the
test cases, not a separate weight in the formula.

## What NOT to do

- Don't add KOBE runtime dependencies. Harness uses `kobe.config` + `kobe.gestures.classifier` only (both already installed).
- Don't commit `results.tsv` — it's untracked, local-only.
- Don't rewrite `synth.py` to make the numbers go up. The dataset is the contract; if you want harder test cases, *add* them.
- Don't break public API (`GestureClassifier.push`, `GestureEvent`, the config fields).
- Don't touch `camera.py` / `service.py` during tuning — those are runtime I/O, not the unit under test.

## Stopping

Manual: user interrupts or we decide marginal gains are gone. Leave the branch
and `results.tsv` intact. Summarize: how many experiments ran, best score vs
baseline, the diff that produced it, and which directions were dead ends.
