# Bot Architecture Conventions

Purpose: preserve consistent dependency direction, module ownership, and naming conventions across bot edits.

Scope:

1. This file defines architecture and API contract rules.
2. Formatting/style choices are out of scope here and live in `.github/BOT_STYLE_GUIDE.md`.

## Canonical Layering

Primary flow:

1. interfaces -> services -> repositories/domain -> database

Do not invert this flow.

## Allowed and Disallowed Dependencies

Allowed:

1. `trading/interfaces/*` importing `trading/services/*`
2. `trading/services/*` importing `trading/repositories/*` and `trading/domain/*`
3. `trading/repositories/*` importing `trading/database/*` helpers

Disallowed:

1. `trading/domain/*` importing interfaces/repositories/database modules
2. `trading/repositories/*` importing CLI/runtime adapters
3. `trading/interfaces/*` embedding persistence SQL or domain policy math that belongs in lower layers

## Package Ownership Map

1. `trading/interfaces/cli/`: CLI adapters and command wiring
   - Keep transport/input wiring here, not domain logic.

2. `trading/interfaces/runtime/jobs/`: scheduler/runtime entrypoints
   - Scheduler and runtime orchestration entrypoints (daily runs, health checks, registration tasks).

3. `trading/interfaces/runtime/data_ops/`: operator-facing maintenance flows
   - Operator-facing DB admin/export flows.
   - Canonical location for backup/export/delete operations.

4. `trading/services/`: application orchestration and composition
   - Coordinates domain logic and repositories.

5. `trading/domain/`: pure policy/decision logic (side-effect free)
   - No DB, CLI, subprocess, or network side effects.

6. `trading/repositories/`: SQL persistence adapters
   - SQL reads/writes and row-level data access helpers.

7. `trading/database/`: DB infrastructure/config/coercion only
   - Schema init/evolution, backend selection, path/config, and coercion helpers.
   - Migration system reference: `docs/architecture/notes-db-migration-system.md`
   - For migration reviews and schema-change validation, use the `DB Migration Steward` bot.

8. `trading/backtesting/`: same layered model within backtesting package
   - Repository/service/domain layering mirrored from main trading module.
   - See `docs/architecture/adr-backtesting-layering.md` for layering rationale.

9. `trading/config/`: file-backed static config assets
   - Account profile presets and other static configuration.

## Constants and Magic Numbers

All bots must follow this rule when writing or reviewing Python code:

1. Do not introduce numeric or string literals that represent a named financial, mathematical, or domain concept inline in logic.
2. Any value that has a name in the domain (e.g., RSI window, annualization factor, basis points divisor, threshold, floor, cap) must be extracted to a named constant in `UPPER_SNAKE_CASE`.
3. Prefer placing shared cross-module constants in `common/constants.py`. Place module-local constants at the top of the file where they are used.
4. Include a short explanatory comment above each constant stating what it represents and why it has that value.
5. This applies to: indicator parameters, time periods, scaling factors, thresholds, allocation percentages, fee/slippage rates, and any other value that encodes domain knowledge.

Examples of violations to flag or fix:
- `returns.std() * (252 ** 0.5)` → should use `TRADING_DAYS_PER_YEAR`
- `elapsed >= interval * 86400` → should use `SECONDS_PER_DAY`
- `slippage / 10_000` → should use `BASIS_POINTS_DIVISOR`
- `if rsi > 70` → should use `RSI_OVERBOUGHT`
- `allocation * 0.10` → should use a named `POSITION_SIZE_PCT` constant

## Naming Conventions

General Python:

1. files/functions/variables: `snake_case`
2. classes/dataclasses: `PascalCase`
3. constants: `UPPER_SNAKE_CASE`

Repository naming:

1. reads: `fetch_*`
2. writes: `insert_*`, `update_*`, `delete_*`

Service naming:

1. read orchestration: `fetch_*`
2. side-effect workflows: `run_*`, `execute_*`
3. input/config derivation: `resolve_*`

Domain naming:

1. prefer descriptive policy/math names
2. avoid transport or persistence verbs

## Import and Facade Rules

1. Prefer direct imports from concrete implementation modules.
2. Avoid adding import-only facades unless they are deliberate public entrypoints.
3. Keep compatibility shims temporary and explicit.

## Abstraction and API Consistency

1. Keep top-level public modules thin and delegate orchestration to services.
2. Keep side-effect-free decision logic in domain modules.
3. Prefer explicit typed interfaces (dataclasses, TypedDict, Protocol) over generic `object` contracts.
4. Keep persistence and transport details out of domain contracts.
5. Avoid API drift: update docs/tests whenever public command/API behavior changes.

## Cross-Platform Safety

1. Use `pathlib`/OS-agnostic joins in Python code.
2. Do not hardcode slash direction (`/` vs `\\`) in runtime logic.
3. Keep command examples runnable from repo root and prefer `python -m ...`.
4. Avoid reliance on case-insensitive path behavior.
5. Make type narrowing explicit where mypy/platform inference may differ.

## Completed Structural Slices

Recent refactors have aligned these areas with repository/service/domain layering:

- Pricing module
- Profiles module
- Reporting module
- Auto-trader orchestration

## Bot Placement Checklist

Before creating or moving code in `trading/`:

1. Classify change target: interface/service/domain/repository/database.
2. Place scheduler operations in `trading/interfaces/runtime/jobs/`.
3. Place operator data ops in `trading/interfaces/runtime/data_ops/`.
4. Keep SQL in repositories, not in handlers/routes.
5. If architecture ownership changes, update this file accordingly.

## Live Trading Safety Guard

The `live_trading_enabled` column on the `accounts` table is a hard safety gate
that prevents live broker orders from being submitted accidentally.

**Rules that all bots must follow without exception:**

1. **Never set `live_trading_enabled = 1`** in any generated code, migration,
   script, fixture, test factory, or seed data.  This flag must only be set
   by a human operator via a direct DB update.

2. **Never modify `broker_type`, `broker_host`, `broker_port`, or
   `broker_client_id`** to point at a live broker endpoint in any generated
   code or automated process.

3. **Never catch or suppress `LiveTradingNotEnabledError`** (from
   `trading.brokers.factory`).  If this error surfaces, it must propagate so
   the operator can investigate.

4. **Test accounts must always have `live_trading_enabled = 0`** (the column
   default).  Never override this in test fixtures or helper factories.

Rationale: `live_trading_enabled = 1` causes real money to move through a
live broker.  No automated process — including bots, CI pipelines, or scripts
— should ever cross this line.
