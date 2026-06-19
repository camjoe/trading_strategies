# Bot Architecture Conventions

Type: architecture
Status: Active
Created: 2026-03-29
Last Reviewed: 2026-06-17
Purpose: Preserve consistent dependency direction, module ownership, naming, and API-contract rules across all edits to the codebase.
Related: [Bot Style Guide](../conventions/bot-style.md), [Service/Repository Boundary](service-repository-boundary.md), [Trading Package Map](../maps/trading-package-map.md)

Scope:

1. This file defines architecture and API contract rules.
2. Formatting/style choices are out of scope here and live in `docs/conventions/bot-style.md`.

## Canonical Layering

Primary flow:

1. interfaces -> services -> repositories/domain -> database

Do not invert this flow.

Top-level package shape is intentionally **hybrid**:

1. The layered backbone above applies to main runtime behavior.
2. Selected bounded contexts remain top-level when their ownership is distinct
   (`trading/backtesting`); broker adapters live at the repo-root `brokers/` package and
   external feature providers live at the repo-root `features/` package.
3. See `docs/maps/trading-package-map.md` for the module directory and `docs/architecture/nav-guide.md` for task-oriented placement guidance.

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
   - Migration system reference: `docs/reference/db-migration-system.md`
   - For migration reviews and schema-change validation, use the `DB Migration Steward` bot.

8. `trading/backtesting/`: same layered model within backtesting package
   - Repository/service/domain layering mirrored from main trading module.
   - See `docs/adr/002-backtesting-layering.md` for layering rationale.

9. `trading/config/`: file-backed static config assets
   - Account profile presets and other static configuration.

10. `features/` (repo root): external-data feature providers for alternative strategies
    - Houses concrete `ExternalFeatureProvider` subclasses (news, social, policy, etc.).
    - This package is the **only** place that may import external API libraries
      (`praw`, `pytrends`, `vaderSentiment`, `newsapi-python`, etc.) or make
      network calls to third-party services.
    - Shared contracts and signal keys live in `trading/domain/feature_provider.py`.
    - `trading/` must never import from `features/`; the interface layer (`trading/interfaces/`)
      is the sole wiring point.
    - Signal functions in `trading/domain/strategy_signals.py` must
      consume feature bundles via injected callables — they must never call external
      APIs directly.

11. `brokers/` (repo root): broker connection adapters and factory
   - Keep all broker SDK imports (ib_async, ibapi) inside this package.
   - Service and domain layers must depend only on `BrokerConnection` from `trading/domain/broker_connection.py`.
   - The factory (`brokers/factory.py`) is the sole location for `broker_type` routing logic.
   - `live_trading_enabled` guard lives here — see Live Trading Safety Guard below.
   - `trading/` must never import from `brokers/`; the interface layer (`trading/interfaces/`) is the sole wiring point.

## External Data Strategies

Rules for all alternative-strategy development (strategy_style = "alternative"):

1. **External calls are isolated in `features/`** — no direct imports of
   `praw`, `pytrends`, `vaderSentiment`, `newsapi`, or any other third-party
   external-data library outside of `features/` submodules.

2. **Graceful degradation** — every `ExternalFeatureProvider._fetch()` implementation
   must catch all exceptions and return `ExternalFeatureBundle(available=False, ...)`.
   Signal functions must check `bundle.available` first and return `"hold"` if `False`.

3. **No API keys in source code** — all credentials are read exclusively from
   environment variables (e.g. `NEWS_API_KEY`, `REDDIT_CLIENT_ID`). Never
   commit secrets to source.

4. **Use the base class** — all external providers must subclass
   `trading.domain.feature_provider.ExternalFeatureProvider`. Do not create
   ad-hoc fetch functions that bypass the caching/TTL/degradation contract.

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
4. model suffixes should reflect lifecycle role:
   - `*Config`: caller-facing, partial, optional input used for create/update flows
   - `*Insert`: repository-ready create payload with required/defaulted/normalized fields
   - `*Record`: persisted read model materialized from database rows

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
4. When a service module is the public entrypoint, do not mirror repository APIs
   with one-line passthrough helpers. Service exports should add validation,
   not-found behavior, orchestration, or caller-facing semantics.
5. See `docs/architecture/service-repository-boundary.md` for the repeatable
   service-vs-repository split used during refactors.

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

## UI Backend Boundary Rule

`paper_trading_ui/backend/services/` is a **transport-only** layer.

It must contain only:
- HTTP request → domain model conversion
- FastAPI-specific error handling (`raise HTTPException`)
- Response payload shaping (producing camelCase dicts for the frontend)

It must **not** contain:
- Domain calculations (equity math, return computations, benchmark overlays)
- Business rules or policy logic
- Data assembly that could be useful to CLI or runtime job consumers

Domain logic belongs in `trading/`.  If a calculation is needed by any interface
(FastAPI, CLI, or runtime jobs), it must live in `trading/services/` or
`trading/domain/`.  The UI backend then delegates to those functions and shapes
the result for the HTTP response.

Violation example: settlement-corrected equity math or benchmark return
calculations in `paper_trading_ui/backend/services/accounts/` — these were
migrated to `trading/services/reporting/` and must not be re-introduced into
the UI backend layer.

## Placement Checklist

Before creating or moving code in `trading/`:

1. Classify change target: interface/service/domain/repository/database.
2. Place scheduler operations in `trading/interfaces/runtime/jobs/`.
3. Place operator data ops in `trading/interfaces/runtime/data_ops/`.
4. Keep SQL in repositories, not in handlers/routes.
5. If architecture ownership changes, update this file accordingly.

For a task-oriented "where do I put X" reference, see `docs/architecture/nav-guide.md`.

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
