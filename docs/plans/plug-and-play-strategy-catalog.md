# Plug-and-Play Strategy Catalog Plan

Type: notes
Status: Active (deferred)
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Capture the deferred P6 plan for making strategy variants and knobs data-driven.
Related: [Plans Index](README.md), [Strategies Reference](../reference/strategies.md), [ADR 011](../adr/011-strategy-catalog-and-parameter-ownership.md)

## Purpose

P6 is the deferred step that would make the existing strategy catalog the canonical runtime source
for strategy definitions and tunable knobs.

## Current State

- `strategies` rows already store the code primitive and `params_json`.
- Runtime strategy resolution still reads `STRATEGY_REGISTRY`.
- Runtime strategy knobs still come from registry `default_params`.
- The `parameters` view exposes strategy knobs, but strategy-knob editing remains view-only until the
  catalog is canonical.

## Intended Shape

- Keep signal primitives in code.
- Treat strategy rows as data definitions: primitive plus knobs, style, required features, status,
  and enabled state.
- Make variants new strategy rows using the same primitive with different knobs.
- Freeze strategies once they have backtest evidence or live usage; tuning creates a new strategy
  row.
- Retire runtime dependence on legacy parameter-set lookups once catalog-backed resolution is in
  place.

## Decisions To Make

- Exact loader and cache behavior for resolving catalog rows into runtime `StrategySpec` values.
- Validation rules for `params_json` against primitive knob schemas.
- Operator edit flow for draft strategy rows and tuned variants.
- Migration path for remaining governance/reporting surfaces that still reference
  `strategy_param_sets`.

## Trigger

Revisit when adding or tuning strategy variants without a deploy becomes a real workflow need.

## Addtional Task
- docs/reference/strategies.md needs to be updated once this plan is resolved (Section title: P6 ongoing work)