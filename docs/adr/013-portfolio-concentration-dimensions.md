# ADR: Portfolio Concentration Dimensions

Type: adr
Status: Accepted
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Record the symbol and sector dimensions used for cross-account portfolio concentration.
Related: [Overview](../overview.md), [Trading Package Map](../maps/trading-package-map.md)

## Context

The portfolio risk rollup needed a concentration definition that could surface cross-account
overlap without introducing new data dependencies. Candidate dimensions included strategy,
instrument symbol, and sector.

## Decision

Measure concentration by symbol and add a sector rollup:

- Symbol concentration is a symbol's share of total cross-account market value from persisted
  positions.
- Cross-account overlap is surfaced as the count of accounts holding that symbol.
- Sector concentration reuses the operator-editable `symbol_sectors.json` reference data.
- Unmapped symbols fall back to `uncategorized`.

Strategy is not a concentration dimension. Strategy exposure is handled by rotation, evaluation, and
allocation reporting rather than instrument-overlap risk.

## Consequences

- The rollup works from existing persisted positions and existing sector reference data.
- Missing sector mappings degrade gracefully.
- Future concentration changes should start in the symbol/sector analysis service and keep CLI/API/UI
  payloads aligned.
