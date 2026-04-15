# Autoresearch: gesture classifier tuning — findings

Branch: `autoresearch/gesture-tuning`

Adapted Karpathy's autoresearch loop (edit → commit → eval → keep/revert)
to `src/kobe/gestures/classifier.py`. Target metric on a 44-case synthetic
dataset (34 train + 10 heldout):

```
score = f1 - 0.005 * mean_latency_frames
```

## Baseline → final

| Metric        | Baseline (main) | Final (this branch) | Δ        |
|---------------|-----------------|---------------------|----------|
| Combined F1   | 0.9552          | **0.9756**          | +0.0204  |
| Precision     | 0.9697          | **1.0000**          | +0.0303  |
| Recall        | 0.9412          | 0.9524              | +0.0112  |
| Latency (frm) | 5.50            | 5.30                | −0.20    |
| Score         | 0.9277          | **0.9491**          | +0.0214  |

**Headline:** precision goes from 97% → **100%** (zero false positives),
F1 up +2%, latency slightly better. The 2 remaining failures are
intentional dataset contradictions.

## The one structural win — static hold-lock (`_static_hold_lock`)

Every other knob I swept was in the noise. The real problem was that a
held pose could re-fire once `gesture_cooldown_ms` expired, because the
vote deque refilled during the hold. The fix:

- After a static fires, record the winning KOBE semantic name.
- Subsequent ticks that vote to the same winner are dropped (no fire).
- Lock clears when the user *actually* releases:
  1. no-hand frame (hand left the camera view), **or**
  2. `_static_release_streak` accumulates `gesture_static_required`
     non-held-consistent frames (unmapped, low-score, or different
     KOBE mapping).
- When the release-streak crosses threshold, the vote buffer is also
  drained — otherwise a sustained `Closed_Fist` misclassification during
  a Thumb_Up hold would clear the lock and immediately fire the opposite
  semantic from those same stale votes.

## Knobs I tried and dropped

| Knob                                | Result  | Why reverted                                                                                        |
|------------------------------------|---------|-----------------------------------------------------------------------------------------------------|
| `gesture_min_score` 0.6 → 0.5       | Reverted | Fixed 1 synthetic FN, created 1 synthetic FP, and production would accept 0.50-0.59 MediaPipe noise. |
| `gesture_static_window` 6 → 8       | Reverted | Lowered the effective debounce ratio from 5/6 (83 %) to 5/8 (63 %). Fragmented votes now fired.     |
| 1-frame swipe-streak grace          | Reverted | No synthetic case exercised it — added code, zero benefit.                                           |

## Dataset contradictions (can't fix)

Two remaining synthetic failures come from the held-out set's intentional
contradictions — same-input, opposite-expected-output cases that no
algorithm can distinguish:

1. **`hard_low_conf_sustained` (TP) vs `hard_score_just_below` (not-fire)**
   — Both are 30 frames of Thumb_Up at scores 0.55–0.59. Same MediaPipe
   signal, opposite expected outcomes. Any threshold choice fixes one and
   breaks the other.
2. **`hard_brief_but_intentional` (TP) vs `hard_static_only_4_of_6`
   (not-fire)** — Both are 4 contiguous Thumb_Up frames at high score.
   Debounce can't distinguish a brief deliberate gesture from a 4-frame
   noise spike.

## Codex iterations — 12 rounds

Ran `codex review --base main` after each substantive change. Codex found
real bugs every round until round 10 when it started signing off on the
classifier. Finally round 12 cleared the patch entirely.

| Round | Severity | Issue                                                                                  | Fix |
|-------|----------|----------------------------------------------------------------------------------------|-----|
| 1 P1  | High     | Hold-lock cleared on transient unmapped frames → duplicate fires on flicker             | Preserve lock across unmapped/low-score |
| 1 P2  | Med      | `setdefault` didn't override shell `KOBE_ENV_FILE`                                      | Unconditional assignment |
| 2 P1  | High     | Previous fix stranded in-frame release — user can't re-fire                            | `_static_unmapped_streak` gate by `static_required` |
| 2 P2  | Med      | `KOBE_ENV_FILE` set after `kobe.config` import — no effect                              | Move to module top |
| 3 P1  | Med      | `NUL`/`/dev/null` doesn't satisfy `is_file()`                                           | Ship real empty.env (later removed) |
| 3 P2  | Med      | KOBE-name lock stuck on same-semantic raw switch (Thumb_Up → Open_Palm)                | Raw-label lock — later reverted |
| 4 P1  | High     | Raw-label lock duplicate-fired on long same-semantic flicker                           | Back to KOBE-name lock (Codex R3 P2 accepted tradeoff) |
| 4 P2  | Med      | `gesture_min_score=0.5` lets production fire on noisy 0.50–0.59 predictions             | Revert to 0.6 |
| 5 P2  | Med      | `harness.py` ran direct didn't preload env                                              | Module-top preload (later replaced) |
| 5 P3  | Low      | TSV description could contain tab/newline → corrupt rows                                | Sanitize description before write |
| 6 P1  | High     | Single cross-mapped frame (Closed_Fist during Thumb_Up) cleared lock → duplicate fire   | Unify release streak to count any non-held-consistent frame |
| 6 P2  | Med      | `harness.py` import mutated global env, broke production `Settings()` resolution       | Scoped save/restore (later replaced) |
| 7 P1  | High     | Release-streak crossed threshold → vote buffer still had 5 opposite-semantic votes → fired wrong gesture | Drain vote buffer on release |
| 7 P2  | Low      | `config/.env.example` still hardcoded old value                                         | Sync to new default (later reverted too) |
| 8 P2  | Med      | Direct pose-switch now pays 4-frame latency penalty                                     | Documented as design tradeoff (vs cross-semantic false fires) |
| 9 P1  | High     | `static_window` 6→8 lowered debounce ratio                                              | Revert |
| 10 P2 | Med      | Crashes weren't logged in `results.tsv`                                                 | Try/except writes `crash` row |
| 10 P2 | Med      | Typo'd `--param` silently dropped                                                       | Validate against `Settings.model_fields` |
| 11 P2 | Med      | Scoped env override didn't help when `kobe.config` pre-imported                        | `_pristine_settings(_env_file=None, _env_prefix="NEVER_MATCH_")` |
| 12    | —        | **No issues found.**                                                                    | — |

## Regression tests added (canaries)

Each Codex finding got a named test case so the bug can't silently return:

- `hard_flicker_during_hold` — 1 unmapped frame every 10 during a long hold
- `hard_relax_inframe_then_refire` — 46 unmapped frames between two Thumb_Up fires
- `hard_long_same_semantic_flicker` — 60 frames alternating Thumb_Up/Open_Palm
- `hard_cross_mapping_flicker` — 1 Closed_Fist every 10 during Thumb_Up hold
- `hard_cross_mapping_sustained` — 5 consecutive Closed_Fist frames during Thumb_Up hold
- `hard_direct_pose_switch` — Thumb_Up hold → direct Closed_Fist (verifies dismiss still fires)
- `hard_fragmented_votes` — 3T + 3V + 2T (5 T's in 8 frames, must not fire 5-of-6)

## What I learned

1. **Dataset contradictions are useful.** The agent who hardened the
   dataset deliberately introduced same-input opposite-expected pairs.
   They're the "hard floor" on the benchmark score, and they correctly
   rejected over-eager knob sweeps that tried to satisfy one at the cost
   of the other.

2. **Codex review is invaluable on subtle-logic changes.** The hold-lock
   went through 7 substantive iterations. Each round caught a real user-
   visible bug I would have missed. The eventual design
   (KOBE-semantic lock + unified release streak + vote-buffer drain on
   release) is considerably more robust than my initial implementation.

3. **Benchmarks miss real-world concerns.** The `min_score=0.5` win on
   the benchmark was a net loss in the real world, because the synthetic
   dataset can't model "users wave their hand at low confidence all day".
   Codex R4 P2 caught this. I reverted despite the synthetic gain.

4. **Widening the debounce window ≠ free latency.** My `static_window`
   6→8 change preserved F1 on the benchmark (no case exercised the new
   ratio) but lowered the effective 5-of-N requirement from 83 % to 63 %.
   Codex R9 caught it via a hypothetical that my dataset didn't.

5. **Determinism in the eval harness matters.** Five rounds of Codex
   feedback went into making `results.tsv` reproducible regardless of
   the developer's `config/.env`, shell env vars, or Python import order.
   The final `_pristine_settings()` factory is the clean answer.
