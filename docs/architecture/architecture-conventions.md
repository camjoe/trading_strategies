# Bot Architecture Conventions

Type: architecture
Status: Active
Created: 2026-03-29
Last Reviewed: 2026-06-17
Purpose: Preserve consistent dependency direction, module ownership, naming, and API-contract rules across all edits to the codebase.
Related: [General Style](../conventions/general-style.md), [Service/Repository Boundary](service-repository-boundary.md), [Trading Package Map](../maps/trading-package-map.md)

Scope:

1. This file defines architecture and API contract rules.
2. Formatting/style choices are out of scope here and live in `docs/conventions/general-style.md`.

## Canonical Layering

Primary flow:

1. interfaces -> services -> repositories/domain -> database

Do not invert this flow.

Top-level package shape is intentionally **hybrid**:

1. The layered backbone above applies to main runtime behavior.
2. Selected bounded contexts remain top-level when their ownership is distinct
   (`src/trading/backtesting`); broker adapters live at the repo-root `src/infrastructure/brokers/` package,
   external feature providers live at the repo-root `src/infrastructure/feature_providers/` package, and the
   concrete market-data adapter + factory live at the repo-root `src/infrastructure/market_data/` package.
3. See `docs/maps/trading-package-map.md` for the module directory and `docs/architecture/nav-guide.md` for task-oriented placement guidance.

## Allowed and Disallowed Dependencies

Allowed:

1. `src/trading/interfaces/*` importing `src/trading/services/*`
2. `src/trading/services/*` importing `src/trading/repositories/*` and `src/trading/domain/*`
3. `src/trading/repositories/*` importing `src/infrastructure/database/*` helpers

Disallowed:

1. `src/trading/domain/*` importing interfaces/repositories/database modules
2. `src/trading/repositories/*` importing CLI/runtime adapters
3. `src/trading/interfaces/*` embedding persistence SQL or domain policy math that belongs in lower layers

## Package Ownership Map

1. `src/trading/interfaces/cli/`: CLI adapters and command wiring
   - Keep transport/input wiring here, not domain logic.

2. `src/trading/interfaces/runtime/jobs/`: scheduler/runtime entrypoints
   - Scheduler and runtime orchestration entrypoints (daily runs, health checks, registration tasks).

3. `src/trading/interfaces/runtime/data_ops/`: operator-facing maintenance flows
   - Operator-facing DB admin/export flows.
   - Canonical location for backup/export/delete operations.

4. `src/trading/services/`: application orchestration and composition
   - Coordinates domain logic and repositories.

5. `src/trading/domain/`: pure policy/decision logic (side-effect free)
   - No DB, CLI, subprocess, or network side effects.
   - Holds logic + DI contracts (`BrokerConnection`, `FeatureFetcherSet`,
     `StrategySpec`). Passive data classes belong in `models/` (see below);
     the deferred exception is the policy-knob `*Settings` dataclasses, which
     stay with their constants until those constants get a dedicated home.

6. `src/trading/models/`: passive data contracts (the lowest layer)
   - Holds **all** passive data contracts: `*Config`/`*Insert`/`*Record`,
     state/order models, and domain value objects (evaluation/promotion/sleeve).
   - No business logic, no I/O, and **no imports from `domain`, `services`,
     `repositories`, `interfaces`, or `infrastructure`** — enforced by
     `scripts/checks/layer_check.py`. `domain` may import `models`, never the reverse.
   - Organized into feature subfolders (`accounts/`, `sleeves/`, `evaluation/`, …),
     one contract per file. See `docs/adr/005-models-as-lowest-data-layer.md`.

7. `src/trading/repositories/`: SQL persistence adapters
   - SQL reads/writes and row-level data access helpers.

8. `src/infrastructure/database/`: DB infrastructure/config/coercion only
   - Schema init/evolution, backend selection, path/config, and coercion helpers.
   - Migration system reference: `docs/reference/db-migration-system.md`
   - For migration reviews and schema-change validation, use the `DB Migration Steward` bot.

9. `src/trading/backtesting/`: same layered model within backtesting package
   - Repository/service/domain layering mirrored from main trading module.
   - See `docs/adr/002-backtesting-layering.md` for layering rationale.

10. `src/infrastructure/config/`: file-backed static config assets
   - Account profile presets and other static configuration.

11. `src/infrastructure/feature_providers/` (repo root): external-data feature providers for alternative strategies
    - Houses concrete `ExternalFeatureProvider` subclasses (news, social, policy, etc.).
    - This package is the **only** place that may import external API libraries
      (`praw`, `pytrends`, `vaderSentiment`, `newsapi-python`, etc.) or make
      network calls to third-party services.
    - Shared contracts and signal keys live in `src/trading/domain/feature_provider.py`.
    - `src/trading/` must never import from `src/infrastructure/feature_providers/`; the interface layer (`src/trading/interfaces/`)
      is the sole wiring point.
    - Signal functions in `src/trading/domain/strategy_signals.py` must
      consume feature bundles via injected callables — they must never call external
      APIs directly.

12. `src/infrastructure/brokers/` (repo root): broker connection adapters and factory
   - Keep all broker SDK imports (ib_async, ibapi) inside this package.
   - Service and domain layers must depend only on `BrokerConnection` from `src/trading/domain/broker_connection.py`.
   - The factory (`src/infrastructure/brokers/factory.py`) is the sole location for `broker_type` routing logic.
   - `live_trading_enabled` guard lives here — see Live Trading Safety Guard below.
   - `src/trading/` must never import from `src/infrastructure/brokers/`; the interface layer (`src/trading/interfaces/`) is the sole wiring point.

13. `src/infrastructure/market_data/` (repo root): concrete market-data adapters and provider factory
   - Keep the `yfinance` SDK import inside this package (`providers.py`).
   - Service and domain layers must depend only on the `MarketDataProvider` port from
     `src/trading/services/market_data/protocols.py` and an injected instance — never the concrete adapter.
   - The factory (`src/infrastructure/market_data/factory.py`) is the sole location for `provider` routing
     (env/config resolution) and concrete-adapter construction (`build_provider`).
   - `src/trading/` must never import from `src/infrastructure/market_data/`; the interface layer
     (`src/trading/interfaces/`) and the backtest composition seam (`src/trading/backtesting/backtest.py`)
     are the only wiring points. This boundary is enforced by `scripts/checks/layer_check.py`.
   - The feature provider (`ProxyFeatureDataProvider`) stays in `src/trading/services/market_data/` — it is a
     trading-domain computation over an injected market-data provider, with no external-library dependency.

## External Data Strategies

Rules for all alternative-strategy development (strategy_style = "alternative"):

1. **External calls are isolated in `src/infrastructure/feature_providers/`** — no direct imports of
   `praw`, `pytrends`, `vaderSentiment`, `newsapi`, or any other third-party
   external-data library outside of `src/infrastructure/feature_providers/` submodules.

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
3. Prefer placing shared cross-module constants in `src/common/constants.py`. Place module-local constants at the top of the file where they are used.
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

"runtime" naming:

1. In a package/module **path**, "runtime" means the scheduler transport layer;
   `src/trading/interfaces/runtime/` is the only place that meaning applies.
2. Operator-tunable settings applied during operation (evaluation confidence,
   promotion policy, trade throttles) live in
   `src/trading/services/operational_settings/`. Do not reintroduce
   `runtime_settings`/`runtime_throttle` packages.
3. In-package `runtime_*` qualifiers (e.g. `services/auto_trading/runtime*.py`)
   meaning "runtime-execution code vs. decision/input code" are intentional.
4. Rationale and rejected alternatives: `docs/adr/004-runtime-naming-and-operational-settings.md`.

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

`apps/paper_trading_web/backend/services/` is a **transport-only** layer.

It must contain only:
- HTTP request → domain model conversion
- FastAPI-specific error handling (`raise HTTPException`)
- Response payload shaping (producing camelCase dicts for the frontend)

It must **not** contain:
- Domain calculations (equity math, return computations, benchmark overlays)
- Business rules or policy logic
- Data assembly that could be useful to CLI or runtime job consumers

Domain logic belongs in `src/trading/`.  If a calculation is needed by any interface
(FastAPI, CLI, or runtime jobs), it must live in `src/trading/services/` or
`src/trading/domain/`.  The UI backend then delegates to those functions and shapes
the result for the HTTP response.

Violation example: settlement-corrected equity math or benchmark return
calculations in `apps/paper_trading_web/backend/services/accounts/` — these were
migrated to `src/trading/services/reporting/` and must not be re-introduced into
the UI backend layer.

## Placement Checklist

Before creating or moving code in `src/trading/`:

1. Classify change target: interface/service/domain/repository/database.
2. Place scheduler operations in `src/trading/interfaces/runtime/jobs/`.
3. Place operator data ops in `src/trading/interfaces/runtime/data_ops/`.
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
