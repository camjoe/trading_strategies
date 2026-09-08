# ADR: Optimizer Experiments Are the Research Evidence Source

Type: adr
Status: Accepted
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Records that promotion, rotation, and the evaluation artifact read walk-forward optimizer experiments — not standalone backtests or the retired rolling-window grouping — and why that consolidation was necessary.
Related: [Backtesting](../reference/backtesting.md), [DB Schema](../reference/db-schema.md), [ADR 014 Execution Mode Collapse](014-execution-mode-collapse.md)

## Context

Two walk-forward implementations existed side by side.

The older `backtest-walk-forward` ran a fixed strategy across chronologically shifted windows and
grouped the results into `walk_forward_experiments`/`walk_forward_windows`. This is rolling-window
robustness testing: it never trained candidates on an earlier interval, froze a winner, or used an
untouched holdout.

The walk-forward optimizer (`backtest-optimize`, revisions `0021`–`0024`) does all three, plus a
per-window baseline comparison and a persisted multiple-testing audit trail.

The optimizer was never wired to the consumers the older path fed, which produced a **stranded
evidence chain**. The consequences were measurable rather than theoretical — on the development
database, all 416 `backtest_runs` rows were optimizer-written (`walk_forward_oos` /
`final_holdout`), leaving **zero** `standalone` runs. Because the evaluation artifact resolved
backtest evidence through a `purpose = 'standalone'` filter and walk-forward evidence through the
older tables, this meant:

- every account was blocked at `candidate` on `RESEARCH_EVIDENCE_REQUIRED`;
- `compute_blended_score` received no inputs and returned `None`;
- the live rotation score degraded to `regime_fit` plus three zeros, including a `stability`
  component built days earlier specifically to derive from real evidence.

The rigorous methodology could not satisfy the promotion gate *by construction*, while the weaker
one was the only thing that could.

Alternatives considered: keep standalone backtests as the backtest-evidence source and repoint only
the walk-forward half (rejected — leaves two evidence producers feeding one gate); leave both paths
and document the split (rejected — the whole problem was two ways to do one thing).

## Decision

**A strategy's research evidence is its most recent completed optimization experiment.**

- **Backtest evidence** is the experiment's untouched **holdout run**. This is the one run whose
  parameters *and* date range were committed before it executed, which is what makes it evidence
  rather than a self-selected result.
- **Walk-forward evidence** is the experiment's per-window **out-of-sample record**, with each
  window return derived from its linked run's equity marks rather than a stored aggregate, so the
  distribution cannot drift from the runs it summarizes.

An experiment counts as evidence for a strategy when it either **targeted** it (`strategy_id`) or
**produced** it (`promoted_strategy_id`). The second clause matters: a promoted variant inherits the
experiment that minted it, whose holdout ran exactly that variant's parameters, so the
optimize→promote loop does not terminate in a strategy the rest of the system considers unevidenced.
Failed experiments are excluded — they carry no winner, no holdout, and no audit tree.

Standalone `backtest` remains as an **exploration tool** and stops being promotion evidence. The
rolling-window stack was deleted entirely (revision `0027`): running `backtest-optimize` with a
single-candidate search space reproduces it exactly and adds a baseline and a holdout, so it
produced no evidence the optimizer cannot.

## Consequences

- Promotion and rotation now require an optimizer run. This is deliberate — a strategy should not be
  promotable on a single backtest over an operator-chosen window — but it makes `backtest-optimize`
  a prerequisite rather than an optional deep-dive.
- **Caveat on attribution.** When an experiment *targeted* a strategy rather than producing it, the
  holdout ran the tuned winner's parameters, not the strategy's defaults. Those numbers are an upper
  bound for that strategy family. Evidence attributed via `promoted_strategy_id` has no such gap.
- `EvaluationWalkForwardEvidence` carries `window_returns` (the full distribution), which let
  rotation `stability` become a real standard deviation instead of a best/worst range that one
  outlier window could dominate.
- The backtest-freshness advisory was recalibrated from 3 days to 30. Three days was tuned to a
  daily refresh job (since retired); on-demand optimizer evidence needs a threshold measured in
  weeks. It remains advisory and never blocks promotion.
- A database reset blanks all research evidence: every account returns to `candidate` until fresh
  optimizer runs exist. Correct behavior, but worth sequencing around.
