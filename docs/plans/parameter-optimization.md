# Parameter Optimization Plan

Type: notes
Status: Active (deferred)
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Capture the deferred P11 plan for systematic strategy-parameter optimization.
Related: [Plans Index](README.md), [Backtesting Reference](../reference/backtesting.md), [Strategies Reference](../reference/strategies.md)

## Purpose

P11 would add a disciplined parameter-search workflow for strategy knobs. It is deferred until manual
strategy tuning becomes a bottleneck.

## Current State

- The `strategies` catalog is canonical at runtime (P6, delivered): tuned variants are new catalog
  rows created via `create-strategy-variant`, so parameter optimization can write variants safely.
- Backtesting and walk-forward workflows exist and should be the validation backbone.

## Decisions To Make

- Search method: grid, random, walk-forward-embedded, or another bounded approach.
- Required out-of-sample or walk-forward validation before a tuned variant is eligible.
- Promotion criteria for creating a new strategy row from a tuned candidate.
- Guardrails against overfitting, excessive turnover, and benchmark-only improvements.

## Constraints

- Optimization results must create new immutable strategy variants, not mutate evidence-backed rows
  (the catalog's freeze guard already enforces draft-only edits).
- The workflow must compare tuned results against simple baselines and the existing default variant.

## Trigger

Revisit when there is demand for systematic parameter sweeps and enough historical data to validate
them honestly.
