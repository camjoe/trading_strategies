# Trading Architecture Guide

Purpose: single source of truth for trading project structure, ownership boundaries, naming conventions, and active cleanup priorities.

## Canonical Package Map

- `trading/interfaces/cli/`
  - CLI adapters (parser composition and command handlers).
  - Keep transport/input wiring here, not domain logic.

- `trading/interfaces/runtime/jobs/`
  - Scheduler and runtime orchestration entrypoints (daily runs, health checks, registration tasks).

- `trading/interfaces/runtime/data_ops/`
  - Operator-facing DB admin/export flows.
  - Canonical location for backup/export/delete operations.

- `trading/services/`
  - Application orchestration that coordinates domain logic and repositories.

- `trading/domain/`
  - Pure policy and decision logic.
  - No DB, CLI, subprocess, or network side effects.

- `trading/repositories/`
  - SQL persistence adapters and row-level data access helpers.

- `trading/database/`
  - DB infrastructure only: schema init/evolution, backend selection, path/config, and coercion helpers.

- `trading/backtesting/`
  - Backtesting feature package with its own repository/service/domain layering.
  - See `docs/architecture/backtesting-layering-adr.md` for backtesting-specific layering decisions.

- `trading/config/`
  - File-backed static config assets (for example account profile presets).

## Dependency Direction

Preferred direction:

1. Interfaces -> Services -> Repositories/Domain -> Database infrastructure.
2. Domain modules must not import interface or infrastructure modules.
3. Repositories should not depend on CLI/runtime adapters.
4. Runtime jobs should orchestrate via services and interfaces, not duplicate domain or persistence logic.

## Naming Conventions

- Repositories (`trading/repositories/*`)
  - Reads: `fetch_*`
  - Writes: `insert_*`, `update_*`, `delete_*`

- Services (`trading/services/*`, `trading/backtesting/services/*`)
  - Read orchestration: `fetch_*`
  - Side-effect workflows: `run_*` or `execute_*`
  - Input/config derivation: `resolve_*`

- Domain (`trading/domain/*`, `trading/backtesting/domain/*`)
  - Prefer descriptive policy/math names.
  - Avoid transport and persistence verbs.

- Compatibility shims
  - Keep temporary and explicit.
  - New internal code should not add new imports to shim paths.

## Import Rules

- Prefer direct imports from concrete modules.
- Avoid import-only facades unless they are the declared public entrypoint.
- New code should target canonical runtime data-ops modules instead of compatibility paths under `trading/database/`.

## Next Recommended Cleanup Step

Highest-value next structural slice:

1. Continue thinning `trading/auto_trader.py` by moving persistence and orchestration helpers behind repository/service adapters.
2. Keep `trading/accounting.py`, `trading/accounts.py`, `trading/pricing.py`, `trading/profiles.py`, and `trading/reporting.py` focused on public APIs while repositories own SQL and services own presentation/orchestration helpers.
3. Keep `trading/database/` focused on DB infrastructure concerns only.

Why this next step:

- The remaining highest-churn trading entrypoint is still `trading/auto_trader.py`.
- Recent slices already moved UI/backend, account-listing, trade-persistence, pricing/profile/reporting orchestration, and much of auto-trader runtime wiring toward canonical repository/service boundaries.
- Keeping pressure on the largest orchestration module yields the most structural clarity per change.

## Bot Orientation Checklist

When a bot is asked to place or refactor code in `trading/`:

1. Determine whether the change is interface, service, domain, repository, or DB infrastructure.
2. Place runtime schedulers in `trading/interfaces/runtime/jobs/`.
3. Place operator-facing DB utilities in `trading/interfaces/runtime/data_ops/`.
4. Keep SQL in repositories or backtesting repositories, not in routes/CLI handlers.
5. Update this file when ownership or conventions change.
