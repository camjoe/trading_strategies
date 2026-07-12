# Plug-and-Play Strategy Catalog Plan (P6)

Type: notes
Status: Active (in progress) — branch `features/strategy-catalog-canonical`
Created: 2026-07-09
Last Reviewed: 2026-07-12
Purpose: Active implementation plan for making the `strategies` catalog the canonical runtime source
for strategy definitions and tunable knobs.
Related: [Plans Index](README.md), [Strategies Reference](../reference/strategies.md), [ADR 011](../adr/011-strategy-catalog-and-parameter-ownership.md)

## Goal

Make the database `strategies` catalog canonical at runtime: knobs and signal-primitive resolution
read from catalog rows, not the code registry. Signal *primitives* stay in code; a strategy row binds
a primitive to a concrete knob dict, so a new *variant* becomes a pure data change (new row) with no
deploy.

## Current state (what already exists)

- **Code half** — `PRIMITIVE_CATALOG` + `resolve_primitive` + `PrimitiveSpec`
  (`src/trading/domain/strategy_signals.py`): each primitive's signal fn + knob schema.
- **Data half** — `strategies` table; `StrategyRepository` with the draft-only immutability guard
  and `freeze`; `StrategyRecord`; `seed_strategy_catalog` seeds rows from `PRIMITIVE_CATALOG`.
- **Assignment is already catalog-keyed** — `book_strategy_assignments.strategy_id → strategies`;
  `BookAssignmentView.strategy_name` is the row's `strategy_key`.
- **Parameters surface** already shows strategy rows (primitive/style/status/params) — read-only.
- The execution seam `generate_book_trade_intents(conn, ...)` holds both the `conn` and the
  assignment, so catalog-backed resolution is a localized change.

## The two gaps (read path still runs off code)

1. **Knobs** — `resolve_strategy_params` returns the registry `default_params`, ignoring the row's
   `params_json` and the assignment.
2. **Signal resolution** — `resolve_strategy` resolves the signal fn via `STRATEGY_REGISTRY`
   name/alias/keyword, not via the assigned row's `primitive` → `PRIMITIVE_CATALOG`. A data variant
   (new key, same primitive, different knobs) cannot run yet.

## Resolved design decisions

1. **Loader/cache** — `resolve_catalog_strategy(conn, strategy_key)` in the `strategy_catalog`
   service returns `(PrimitiveSpec, effective_params)`, where `effective_params` = primitive
   `knob_schema` defaults merged **under** the row's `params_json`. No caching (catalog is tiny,
   local SQLite; read on demand).
2. **Validation** — `validate_params_against_primitive(primitive, params)` in the domain: on write,
   reject keys outside the primitive's `knob_schema` and non-coercible types; on read, merge over
   defaults so partial/stale JSON never reaches a signal fn.
3. **Edit flow** — mirror `configure-book-rotation-policy`: `configure-strategy` (edit a draft's
   knobs/enabled), `create-strategy-variant` (new draft row, same primitive, new key),
   `freeze-strategy`. The repo guard already enforces draft-only edits.
4. **Legacy `strategy_param_sets`** — retire the readers within P6 (scope confirmed 2026-07-12).
   Assignments already resolve params via `strategy_id`, so `param_set_id` is redundant.

## Phased plan

| Phase | Work |
|---|---|
| **P6-1** | Catalog-backed **knob** resolution: `resolve_catalog_strategy`; rewire `resolve_strategy_params` to read `params_json` (merged over primitive defaults) via the assignment's `strategy_key`. + tests |
| **P6-2** | Catalog-backed **signal** resolution: resolve the signal fn through the row's `primitive` → `PRIMITIVE_CATALOG`; retire runtime dependence on `STRATEGY_REGISTRY` (keep it as the seed + alias-compat source only). + tests |
| **P6-3** | Validation + **edit surface**: `validate_params_against_primitive`; `configure-strategy` / `create-strategy-variant` / `freeze-strategy` mutations + CLI; make the parameters surface editable. + tests |
| **P6-4** | Retire legacy `strategy_param_sets` readers (governance/reporting); drop `param_set_id` from the write path (DB column drop deferred to a data-op). + tests |
| **P6-5** | Docs: finish the truncated "P6 ongoing work" section in `strategies.md`; update `overview.md` known-gaps; mark P6 delivered in `status.md`; update ADR 011 consequences; retire this plan file. |

## Constraints

- Touches `src/trading/` — follow the layering (interfaces → services → domain/repositories → db);
  resolver in services/domain, CLI in interfaces, no dependency inversion.
- Keep signal primitives in code; only definitions/knobs go data (no arbitrary-logic DSL).
- Freeze strategies once they have evidence or live usage; tuning creates a new row.
- Validate each phase with its matching `run suite` before committing.

## Additional task

- `docs/reference/strategies.md` "P6 ongoing work" section is truncated mid-sentence and must be
  completed when this plan resolves (part of P6-5).
