# ADR: Strategy Catalog and Parameter Ownership

Type: adr
Status: Accepted
Created: 2026-07-09
Last Reviewed: 2026-07-12
Purpose: Record where strategy knobs and execution settings belong after the clean schema rewrite.
Related: [Strategies Reference](../reference/strategies.md)

## Context

The pre-rewrite model mixed several concepts: strategy identity, tunable strategy knobs, account
execution settings, and parameter sets. The clean schema needed a shape that avoided a broad
god-table while still allowing future data-defined strategy variants.

## Decision

Separate parameter ownership by concern:

- Strategy knobs live with strategy rows as `params_json`.
- Signal primitives and knob schemas stay in code.
- Execution, risk, option, and rotation settings live in typed book settings tables keyed to
  `books`.
- Global operational settings remain separate from per-book settings.
- The unified parameter source is a read/edit surface over these stores, not a new consolidated
  persistence model.

Strategies are fixed once they have evidence or live usage. Tuning creates a new strategy row rather
than mutating an evidence-backed definition.

## Consequences

- New strategy variants are data changes: runtime resolution reads the catalog row
  (`resolve_catalog_strategy` — primitive plus `params_json` over the primitive defaults), and
  operators edit via `create-strategy-variant` / `configure-strategy` / `freeze-strategy`.
- The separate parameter-set model is retired: its readers were removed and
  `StrategyParamSetRepository` deleted. The `strategy_param_sets` table and the
  `book_strategy_assignments.param_set_id` column persist (unused, left NULL) until a data-op drops
  them.
- Validation and operator editing follow the owning concern: primitive knob schema for
  strategy rows (`validate_params_against_primitive`), typed columns for book settings, and global
  commands for operational settings.
- Default-tracking is asymmetric by design: the nullable book rotation-policy columns can be
  cleared back to the code default (pass `none` to `configure-book-rotation-policy`), while the
  `NOT NULL` global evaluation/promotion columns pin their values on first edit — an edited global
  setting stops tracking future code-default changes. Accepted because the global columns carry
  schema-level defaults and `CHECK` constraints; revisit only if code defaults start moving often.
