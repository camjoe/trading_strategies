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

1. Keep `trading/auto_trader.py` as a thin public facade over runtime composition in `trading/services/auto_trader_runtime_service.py`.
2. Continue using direct modules under `trading/services/` for orchestration and keep top-level module files as stable entrypoints.
3. Keep `trading/database/` focused on DB infrastructure concerns only.

Why this next step:

- Runtime composition remains the easiest place for boundary drift when new features are added.
- Recent slices have already aligned pricing, profiles, reporting, and auto-trader orchestration with repository/service ownership.
- Keeping this file current avoids reintroducing facade-wrapper churn in top-level modules.

## Bot Orientation Checklist

When a bot is asked to place or refactor code in `trading/`:

1. Determine whether the change is interface, service, domain, repository, or DB infrastructure.
2. Place runtime schedulers in `trading/interfaces/runtime/jobs/`.
3. Place operator-facing DB utilities in `trading/interfaces/runtime/data_ops/`.
4. Keep SQL in repositories or backtesting repositories, not in routes/CLI handlers.
5. Update this file when ownership or conventions change.
