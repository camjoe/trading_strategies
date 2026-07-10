# Backtest Freshness Cadence Plan

Type: notes
Status: Active (deferred)
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Capture the deferred P12 policy work for deciding when backtests should be recalculated.
Related: [Plans Index](README.md), [Backtesting Reference](../reference/backtesting.md), [Runtime Jobs](../reference/runtime-jobs.md)

## Purpose

P12 is a policy decision about how fresh backtest evidence must be for rotation, promotion, and
reporting.

## Current State

- Daily backtest refresh exists as an opt-in runtime job.
- Evaluation can consume backtest, walk-forward, and paper/live evidence.
- No stricter freshness policy is currently required for rotation decisions.

## Decisions To Make

- Freshness thresholds by evidence type and workflow.
- Whether stale evidence blocks decisions or only lowers confidence.
- Operator override behavior for known stale or incomplete runs.
- Reporting needed to surface stale evidence before it affects decisions.

## Constraints

- Freshness rules should not create noisy daily work unless stale evidence is proven harmful.
- Any blocking rule must be visible from scheduler or CLI workflows, not only the UI.

## Trigger

Revisit when stale backtests are observed or suspected to skew rotation, promotion, or governance
outcomes.
