# ADR: Strategy Catalog and Parameter Ownership

Type: adr
Status: Accepted
Created: 2026-07-09
Last Reviewed: 2026-07-09
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

- New strategy variants can become data changes after catalog-backed runtime loading is implemented.
- The separate parameter-set model is legacy surface until remaining readers are retired.
- Validation and operator editing should follow the owning concern: primitive knob schema for
  strategy rows, typed columns for book settings, and global commands for operational settings.
- Default-tracking is asymmetric by design: the nullable book rotation-policy columns can be
  cleared back to the code default (pass `none` to `configure-book-rotation-policy`), while the
  `NOT NULL` global evaluation/promotion columns pin their values on first edit — an edited global
  setting stops tracking future code-default changes. Accepted because the global columns carry
  schema-level defaults and `CHECK` constraints; revisit only if code defaults start moving often.
