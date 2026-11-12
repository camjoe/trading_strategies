# Adaptive Learning Plan (P10)

Type: plan
Status: Active (deferred)
Created: 2026-07-09
Last Reviewed: 2026-10-11
Purpose: Define the staged, evidence-gated plan for a learned layer on top of the static decision score, and the conditions that must hold before any stage starts.
Related: [Overview](../overview.md), [ADR 019](../adr/019-rotation-score-components.md), [Backtesting](../reference/backtesting.md), [Plans Index](README.md)

## Purpose

P10 asks one question: can a learned model make strategy selection, rotation, or sizing decisions
better than the static decision score? The plan stays deferred. This document defines what
evidence starts each stage, so nobody builds the model before the evidence exists.

## Current state

- `derive_decision_score` (`src/trading/domain/evaluation/decision_score.py`) is the only place that
  turns a `StrategyEvaluationArtifact` into an `EvaluationDecisionScore`. Compare, promotion, and
  rotation read this score.
- Rotation persists score and confidence on `rotation_decisions`.
- The strategy advisor records each decision in the write-once `strategy_decisions` ledger. A row
  holds the decision, the rejected alternative, the rationale, and frozen evidence.
- `advisor-score` grades each decision after its outcome window closes (default 21 trading days,
  `DEFAULT_OUTCOME_WINDOW_DAYS`). It backtests both arms over the window that followed, with the
  same engine, universe, sizing, and costs. The verdict is `helped`, `hurt`, or `neutral`. The
  neutral band is 1.0 percentage point (`DECISION_NEUTRAL_BAND_PCT`).
- `advisor-scorecard` groups scored decisions by agent, decision type, or regime. A group is
  rankable at 20 measured decisions (`MIN_DECISIONS_FOR_RANKING`).
- No learned-state table or model exists.

## What the advisor changes

The earlier version of this plan listed three open items. The advisor closes two of them.

| Earlier open item | Status now |
|---|---|
| Learning label ("what is a good decision") | Closed. The counterfactual verdict in `strategy_decisions` is the label. Realized paper return is context only. |
| Decision-snapshot table | Closed. The ledger holds frozen evidence at decision time. Do not add a second table. |
| Learning target, model class, update policy | Open. See Stages. |

## Stages

Each stage has an entry condition. Do not start a stage before its condition holds.

### Stage 0: collect evidence

- Run the advisor on the paper books and score each decision when its window closes.
- Entry condition for Stage 1: at least one scorecard group is rankable (20 measured decisions),
  and the decisions cover more than one regime. Record the counts in the plan before you start.

### Stage 1: offline analysis only

- Build a dataset of ledger rows. The features are the frozen evidence fields. The label is the
  verdict or the measured edge.
- Split by time. Train on older decisions and test on newer ones. Never shuffle.
- Compare these baselines on the test split:
  - the static decision score
  - a random choice
  - a simple heuristic, such as "always hold"
- Use the simplest model that can work, for example a calibrated logistic model.
- Output: a report in `local/`. No code path in the runtime reads it.
- Exit condition: the model beats the static score on the test split, by a margin and over a
  horizon that this plan states before the run.

### Stage 2: advisory re-ranking

- Show the model output in `advisor-digest` as one more review flag. It proposes. It never decides.
- Score its proposals through the same scorecard, as a separate group, so the model gets graded the
  same way as every other agent.
- Exit condition: the model group is rankable and its edge interval is above the static score group.

### Stage 3: decision

- Decide in a new ADR whether the model stays advisory or influences rotation ranking.
- A model that influences ranking needs a kill switch that restores the static score with no
  residual state.

## Constraints

- Keep live execution human-gated. A learned output is a proposal.
- Validate out of sample only. Do not optimize on backtest P&L, because that automates overfitting.
- Keep the layer reversible. Disabling it returns the system to the static score.
- Keep each learned adjustment explainable enough to answer why a strategy was promoted or rotated.
- Put model parameters and research output under `local/`. Do not commit them.

## Open decisions

- The learning target: strategy selection, sizing, or re-ranking of the static score. Start with
  re-ranking, because it is the lowest risk.
- The acceptance margin and horizon for the Stage 1 exit condition.
- The minimum sample size per regime. The scorecard threshold of 20 is a floor for ranking, not
  evidence that a model generalizes.

## Related Docs

- [Overview](../overview.md) — decision score, rotation, and the strategy advisor
- [Backtesting](../reference/backtesting.md) — walk-forward terms and evaluation honesty
- [ADR 019](../adr/019-rotation-score-components.md) — rotation score components
