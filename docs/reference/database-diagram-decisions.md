# Database Diagram Decisions

Type: notes
Status: Active
Created: 2026-07-17
Last Reviewed: 2026-07-17
Purpose: Track database diagram presentation, schema terminology, and schema-visible capability decisions, including deferred follow-up work.
Related: [Database Schema](db-schema.md), [Database Diagram Viewer](database-diagram-viewer.html), [Backtesting](backtesting.md), [Walk-Forward Optimization Plan](walk-forward-optimization-plan.md)

## Purpose

Use this living decision log to preserve the reasoning behind database diagram organization and terminology. Update an entry when its implementation status changes; use an ADR instead if a future decision changes an architectural boundary.

## Decision Log

| Area | Decision | Rationale | Status |
|---|---|---|---|
| Category interaction | Category titles move independently from their associated tables. Individual tables remain draggable. | A title should be positionable without unexpectedly rearranging an entire group. | Implemented |
| Category identification | Table headers carry a subtle tint and accent using their category color. | Tables remain visibly associated with their category after either the title or table is moved. | Implemented |
| Category title sizing | Category titles use a larger label treatment than the original viewer. | Category boundaries should remain easy to scan in a large diagram. | Implemented |
| Backtest snapshots | `backtest_equity_snapshots` belongs to Research with `backtest_runs` and `backtest_trades`, not operational Snapshots and metrics. | It shares the ownership and lifecycle of persisted backtest evaluation output. | Implemented |
| Risk terminology | Treat `risk_decisions` as runtime trade-risk outcomes, not strategy-promotion decisions. Prefer the user-facing label **Trade risk decisions** and consider a future table rename to `trade_risk_decisions`. | The current name is broad enough to be mistaken for promotion governance. Rows specifically record whether a proposed trade was allowed, rescaled, or blocked. | Deferred |
| Promotion terminology | Promotion decisions are the terminal `approved` or `rejected` entries in `promotion_review_events`. A `promotion_reviews` row represents the review case and its current or final state. | This distinguishes the stateful review record from its chronological audit history. | Current behavior; document in future UI/schema descriptions as needed |
| Rotation and promotion | Treat strategy rotation and promotion approval as separate controls unless a future governance decision explicitly links them. | Rotation selects a strategy for a configured book, while promotion records an operator governance outcome. The current schema has no direct relationship enforcing promotion approval before rotation. | Current behavior; gating policy unresolved |
| Walk-forward methodology | Describe the current feature as rolling-window robustness testing, not full train-optimize-test walk-forward optimization. | Persisted walk-forward data contains test-window and grouping metadata but no separate training windows, optimization trials, selection criteria, or frozen parameters for each out-of-sample window. | Current capability boundary; expansion deferred |

## Promotion and Risk Semantics

The promotion lifecycle begins when a `promotion_reviews` row is created in the `requested` state. Its associated `promotion_review_events` history records the initial request, operator notes, and the eventual `approved` or `rejected` decision. Approval records the review outcome; it does not automatically enable live trading.

The `risk_decisions` table belongs to runtime execution safety. Each row explains how the risk gate handled a proposed trade or safety condition using an `allow`, `rescale`, or `block` action plus a reason code and requested/approved sizing context.

## Rotation and Promotion Semantics

A strategy can participate in book rotation before a promotion review approves it, depending on the book's mode and strategy configuration. Promotion approval means that the strategy passed the operator governance workflow; rotation means that the book's configured selection process chose the strategy. A rotation is not a promotion approval, and a promotion approval does not automatically generate a rotation.

`rotation_decisions` can still contribute indirectly to promotion assessment. Its strategy boundaries allow evaluation to isolate the book's equity snapshots for the periods when a particular strategy was active. A later `promotion_reviews` record can freeze the resulting assessment evidence, but there is no foreign key or schema constraint connecting that review to the underlying rotation decisions.

The current schema does not directly enforce that only promotion-approved strategies can rotate into a given execution mode. Whether promotion approval should become a prerequisite for some or all rotation modes remains a separate governance decision.

## Walk-Forward Methodology

The simulator used for a walk-forward window is the same simulator used for a standalone backtest. Each window is therefore persisted as a `backtest_runs` row and reuses the associated `backtest_trades` and `backtest_equity_snapshots`. `walk_forward_group_runs` adds the window's position, date range, return, and membership in a `walk_forward_groups` experiment.

What differs is the experimental design. A single backtest evaluates one continuous historical interval. The current walk-forward workflow evaluates repeated, chronologically shifted test intervals and summarizes their dispersion through average, median, best, and worst returns. This can expose time or regime sensitivity that one long-period result might conceal.

The persisted model currently records:

- overall start and end dates;
- `test_months` and `step_months`;
- each test window's start date, end date, index, run, and return;
- aggregate return statistics across the windows.

It does not currently represent:

- a separate training interval preceding each test interval;
- a parameter search or other optimization performed within that training interval;
- the candidate parameter sets evaluated;
- the objective and selection rule used to choose a candidate;
- the selected parameters frozen before the next out-of-sample test;
- a durable link from each test run to its training and selection artifacts.

For that reason, the persisted capability should be described as **rolling-window robustness testing**. It tests whether a fixed strategy behaves consistently across multiple chronological windows. It should not be presented as full **walk-forward optimization**, which would repeatedly train or optimize on past-only data, freeze the selected configuration, and then evaluate that configuration on the next unseen interval.

This is not a criticism of reusing `backtest_runs`; that reuse is appropriate because each window still performs a backtest simulation. The missing distinction is methodological metadata and orchestration, not a separate trade or equity storage format.

Any future full walk-forward optimization must preserve chronological isolation. Training and parameter selection may use only information available before the associated test window, and the chosen configuration must be frozen before that out-of-sample evaluation begins. Random splits or selection informed by later windows would introduce leakage and would not satisfy this methodology.

## Deferred Follow-up

- Change the diagram's user-facing `risk_decisions` label to **Trade risk decisions**.
- Decide whether the clarity benefit of renaming the physical table to `trade_risk_decisions` justifies a database migration and corresponding code changes.
- Consider renaming **Snapshots and metrics** to **Operational snapshots and metrics** to distinguish runtime measurements from research artifacts.
- Decide whether promotion approval should gate strategy eligibility for any book rotation modes, and where that policy should be enforced.
- Decide whether to rename the current feature and UI label to **Rolling-window evaluation**, or expand it into full walk-forward optimization with persisted training, selection, and frozen-parameter artifacts.

## Boundaries

- Do not interpret a promotion approval as automatic live-trading activation.
- Do not interpret a rotation into a strategy as promotion approval.
- Do not use `risk_decisions` for promotion workflow outcomes.
- Do not describe the current rolling-window persistence model as train-optimize-test walk-forward optimization.
- Keep implemented behavior and deferred proposals visibly distinguished in this document.

## Related Docs

- [Database schema quick reference](db-schema.md)
- [Generated database diagram viewer](database-diagram-viewer.html)
- [Backtesting reference](backtesting.md)
- [Walk-forward optimization plan](walk-forward-optimization-plan.md)
- [Governance review runbook](../runbooks/governance-review.md)
