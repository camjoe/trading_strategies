# Bot Architecture Conventions

Type: architecture
Status: Active
Created: 2026-03-29
Last Reviewed: 2026-07-17
Purpose: Preserve consistent dependency direction, module ownership, naming, and API-contract rules across all edits to the codebase.
Related: [General Style](../conventions/general-style.md), [Service/Repository Boundary](service-repository-boundary.md), [Service Ownership Map](service-ownership.md), [Trading Package Map](../maps/trading-package-map.md)

Scope:

1. This file defines architecture and API contract rules.
2. Formatting/style choices are out of scope here and live in `docs/conventions/general-style.md`.

## Canonical Layering

Primary flow:

1. interfaces -> services -> repositories/domain -> database

Do not invert this flow.

`src/trading/` holds **layers only**. A package that owns its own tables and needs its own
stack to reach them is a bounded context and sits beside `trading/`, not inside it:

1. The layered backbone above applies to main runtime behavior.
2. **The test is table ownership.** `src/backtesting/` owns seven tables whose only runtime writer
   is its own repositories (`backtest_runs`, `backtest_executions`, `backtest_equity_snapshots`,
   `optimization_experiments`, `optimization_windows`, `optimization_trials`,
   `optimization_run_manifests`); every other package under `src/trading/` shares
   `trading/repositories/`. That is why it is the only one, and the criterion a future candidate
   has to meet. Nothing outside `backtesting/` writes those tables — the fixture seeder used to,
   with hand-written SQL that the import-based rule could not see, and now crosses at
   `backtesting.services.fixture_seed` like every other reader.
   Its seam with `trading/` is enforced in both directions
   by `layer_check` — reads cross at services, and shared lower layers (`trading.domain`,
   `trading.models`, `trading.persistence`) are layering rather than crossing. Where a
   *calculation* both contexts need belongs is settled by
   [ADR 020](../adr/020-shared-financial-math-ownership.md): `trading/domain/` owns it,
   `common/` keeps unit scales only, and `backtesting/domain/` keeps what only a backtest
   can compute.
3. Broker adapters live at the repo-root `src/infrastructure/brokers/` package,
   external feature providers live at the repo-root `src/infrastructure/feature_providers/` package, and the
   concrete market-data adapter + factory live at the repo-root `src/infrastructure/market_data/` package.
4. See `docs/maps/trading-package-map.md` for the module directory and `docs/architecture/nav-guide.md` for task-oriented placement guidance.

## Allowed and Disallowed Dependencies

Allowed:

1. `src/trading/interfaces/*` importing `src/trading/services/*`
2. `src/trading/services/*` importing `src/trading/repositories/*` and `src/trading/domain/*`
3. `src/trading/repositories/*` importing `src/infrastructure/database/*` helpers
4. Any layer importing `src/trading/persistence/*` — it sits below the repository
   layer so services, both repository packages, and `backtesting/*` can share
   transaction scope and column encoding without borrowing from one another

Disallowed:

1. `src/trading/domain/*` importing interfaces/repositories/database modules
2. `src/trading/repositories/*` importing CLI/runtime adapters
3. `src/trading/interfaces/*` embedding persistence SQL or domain policy math that belongs in lower layers

## Package Ownership Map

Layer-level ownership **rules**. For what each module in a package actually does, see
[Trading Package Map](../maps/trading-package-map.md); for the boundaries **between service
packages** inside `src/trading/services/`, see [Service Ownership Map](service-ownership.md).

| Package | Rule |
|---|---|
| `trading/interfaces/cli/` | Transport and input wiring only — no domain logic |
| `trading/interfaces/runtime/jobs/` | Scheduler/runtime orchestration entrypoints only (daily runs, health checks, registration tasks) |
| `trading/interfaces/runtime/data_ops/` | Canonical location for operator-facing DB admin/backup/export/delete flows |
| `trading/services/` | Coordinates domain logic and repositories |
| `trading/domain/` | Side-effect free — no DB, CLI, subprocess, or network |
| `trading/models/` | The lowest layer — imports nothing from any other layer |
| `trading/repositories/` | SQL reads/writes and row-level data access helpers |
| `trading/persistence/` | Mechanics shared by all DB access — transaction scope, column encoding. Below the repository layer; imports nothing from `trading/` or `infrastructure/` |
| `backtesting/` (repo root, beside `trading/`) | Bounded context owning the backtest + optimizer tables; mirrors the same repository/service/domain layering |
| `infrastructure/database/` | DB infrastructure only: schema migration, connection gating, backend selection, path/config |
| `infrastructure/config/` | File-backed static config assets (account profile presets) |
| `infrastructure/brokers/` | Owns broker SDK imports and connection adapters |
| `infrastructure/feature_providers/` | Owns external-data SDK imports and network calls |
| `infrastructure/market_data/` | Owns market-data SDK imports and concrete providers |

Layer direction, broker SDK, external-data SDK, market-data adapter, and retired runtime
package-name boundaries are enforced by `python -m scripts.checks.repo.layer_check`.

`trading/services/fixtures/` is an operator tool, not application code: it generates demo and
sandbox databases full of synthetic records. `layer_check` forbids importing it from anywhere
under `src/`, so no runtime behaviour can come to depend on generated data. Reach it from a
`scripts/` entry point or a test.

### Detail the one-line rules do not carry

- **`domain/`** holds logic plus DI contracts (`BrokerConnection`, `FeatureFetcherSet`,
  `StrategySpec`); passive data classes belong in `models/`. The deliberate exception is the
  policy-knob `*Settings` dataclasses (`EvaluationConfidenceSettings`,
  `PromotionPolicySettings`) — domain policy parameters, not data contracts, so they stay here
  with the domain math constants they default to.
- **`models/`** holds **all** passive data contracts: `*Config`/`*Insert`/`*Record`,
  state/order models, and domain value objects (evaluation/promotion/books), in feature
  subfolders (`accounts/`, `books/`, …), one contract per file. No business logic, no I/O, and
  **no imports from `domain`, `services`, `repositories`, `interfaces`, or `infrastructure`**.
  `domain` may import `models`, never the reverse. See
  [ADR 005](../adr/005-models-as-lowest-data-layer.md).
- **`brokers/`** — service and domain layers must depend only on `BrokerConnection` from
  `src/trading/domain/broker_connection.py`. The factory
  (`src/infrastructure/brokers/factory.py`) is the sole location for `broker_type` routing.
  Both broker guards live here — the `live_trading_enabled` real-money gate and the IBKR
  paper-account assertion (see [Live Trading Safety Guard](#live-trading-safety-guard)).
- **`feature_providers/`** — houses concrete `ExternalFeatureProvider` subclasses (news,
  social, policy). Shared contracts and signal keys live in
  `src/trading/domain/feature_provider.py`; signal functions in
  `src/trading/domain/strategies/signals/` must consume feature bundles via injected callables.
- **`market_data/`** — service and domain layers must depend only on the `MarketDataProvider`
  port from `src/trading/services/market_data/protocols.py` and an injected instance, never the
  concrete adapter. The factory (`src/infrastructure/market_data/factory.py`) is the sole
  location for `provider` routing (env/config resolution) and concrete-adapter construction
  (`build_provider`). `ProxyFeatureDataProvider` stays in `src/trading/services/market_data/` —
  a trading-domain computation over an injected provider, with no external-library dependency.
- **Migrations** — see [DB Migration System](../reference/db-migration-system.md); use the
  `db-migration` skill (`.ai/skills/db-migration/`) for migration review and schema-change
  validation.
- **`backtesting/`** — see [Backtesting](../reference/backtesting.md) and
  `src/backtesting/README.md`.

  **A bounded context owes the backbone its seam, not its internal conventions.** What crosses
  between `backtesting/` and `trading/` is constrained and enforced by `layer_check`; how
  backtesting is arranged inside is its own business. Recorded because it keeps getting re-asked:

  - It exposes **module-level repository functions** where `trading/repositories/` uses
    `*Repository` classes, and names its modules for what they own with no layer suffix where
    trading uses service packages. Neither is drift — nothing here constrains module filenames
    beyond `snake_case`, `infrastructure/` is mixed the same way, and both packages follow the
    documented `fetch_*`/`insert_*` verbs.

    Backtesting dropped both layer suffixes for the same reason: the suffix repeated the directory
    it sat in. `repositories/*_repository.py` went in 2026-08 and `services/*_service.py` followed,
    leaving `repositories/runs.py` and `services/reporting.py`. That aligned the repository
    filenames with `trading/repositories/` because the old names were redundant on their own terms,
    **not** because matching trading is required — the paragraph above still governs. The
    function-vs-class split was weighed at the same time and deliberately left alone: the classes
    hold only a connection and nothing subclasses or substitutes them, so converting would buy
    symmetry and no behaviour. **This says nothing about `trading/repositories/`,** whose
    `*Repository` classes are settled and are not to be changed on the strength of a decision
    made over here.
  - Its data contracts stay in **its own** `backtesting/models/` package — feature modules with a
    re-exporting root, the same arrangement as `trading/models/`, following the same
    `*Config`/`*Insert`/`*Record` suffixes. Sharing the *shape* is worth it for discoverability;
    sharing the *location* is not. [ADR 005](../adr/005-models-as-lowest-data-layer.md) governs
    `trading/models/` and does not reach across contexts, and moving these in would make trading's
    lowest layer own contracts for seven tables it never writes.
  - Module size is not a reason to split one: `models/optimizer.py` is 494 lines against
    `trading/models/books.py` at 433. ADR 005 moved *toward* grouped feature modules, so a module
    holding one coherent area is the target state, not drift from it.

## Execution and Parameter Ownership

Books are the execution primitive. A book is a bounded pool of capital inside an
account, run to one active strategy assignment with book-keyed rotation,
submission, accounting, risk, and reporting.

Rules:

1. New runtime trading, rotation, risk, accounting, and reporting work should be
   book-keyed unless the change is explicitly about broker account identity,
   custody, credentials, or account-level operator metadata.
2. The default book is the compatibility bridge for account-level workflows.
   Do not reintroduce a separate account-mode execution path or another
   execution primitive.
3. Rotation scheduling is book-owned. `book_rotation_settings` owns the
   per-book rotation gate, schedule, lookback, and cooldown policy. Do not add
   new account-row rotation configuration.
4. Strategy primitives and parameter schemas stay in code. Strategy-specific
   knob values live on strategy rows as `params_json`.
5. Execution, risk, option, goal, and universe settings live as typed columns on `books`.
   Rotation settings remain in `book_rotation_settings` because they form a large, coherent,
   comparatively sparse group.
6. Global operational settings remain separate from per-book settings.
7. `src/trading/services/parameters/` is a read/edit surface over those owning
   stores, not a new consolidated persistence model.

Rationale and delivered cleanup: `docs/adr/010-book-keyed-execution-model.md` and
`docs/adr/014-execution-mode-collapse.md`.

## Database Modeling

1. Prefer typed tables and columns with explicit domain meaning. Do not introduce generic
   entity-attribute-value or category/value storage.
2. Add mapping tables only for genuine many-to-many relationships or when the relationship itself
   carries historical meaning.
3. Physical schema changes use immutable, numbered Alembic revisions. Each revision must provide a
   reversible downgrade; SQLite rebuilds follow the established migration pattern documented in
   `docs/reference/db-migration-system.md`.

## External Data Strategies

Rules for all alternative-strategy development (strategy_style = "alternative"):

1. **Graceful degradation** — every `ExternalFeatureProvider._fetch()` implementation
   must catch all exceptions and return `ExternalFeatureBundle(available=False, ...)`.
   Signal functions must check `bundle.available` first and return `"hold"` if `False`.

2. **Credentials stay out of source** — read them from environment variables
   or other non-committed configuration; `secret_hygiene_check` blocks committed
   literal credentials in source/config files.

3. **Use the base class** — all external providers must subclass
   `trading.domain.feature_provider.ExternalFeatureProvider`. Do not create
   ad-hoc fetch functions that bypass the caching/TTL/degradation contract.

## Constants and Magic Numbers

All agents must follow this rule when writing or reviewing Python code:

1. Do not introduce numeric or string literals that represent a named financial, mathematical, or domain concept inline in logic.
2. Any value that has a name in the domain (e.g., RSI window, annualization factor, basis points divisor, threshold, floor, cap) must be extracted to a named constant in `UPPER_SNAKE_CASE`.
3. Place each constant at its **lowest owning layer**: the lowest layer that owns
   the concept *and* is reachable by every consumer without forcing an upward
   import. Sort by the constant's nature, not by convenience:

   | Constant kind | Home |
   |---|---|
   | Generic, domain-agnostic primitive used across unrelated areas (time, math, basis points, indicator params) | `src/common/constants.py` |
   | A feature's data-contract vocabulary or schema metadata (allowed `status`/`stage` values, artifact/schema versions) | that feature's `constants.py` at its lowest owning layer — e.g. `src/trading/models/<area>/constants.py` |
   | Domain policy parameters (math weights, thresholds, gate/decision messages) | the owning `src/trading/domain/` module (module-local or an area constants module) |
   | One-off value used in a single file | top of that file |

   This respects layer direction (`domain` may import `models`/`common`; `models`
   may import only `common`; nothing imports upward), so a constant never drags a
   consumer into an illegal import. Feature data-vocabulary living in
   `models/<area>/constants.py` is intentional — `domain` policy *reads* the
   vocabulary from the data layer, which is the correct direction. See
   `docs/adr/005-models-as-lowest-data-layer.md`.
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
4. value/object construction (dataclass, dict, config text, id, connection): `build_*`
5. operator-facing display text (`str`/`list[str]`): `render_*`, kept in a
   `presentation.py` module. Do not spell display builders `build_*` or
   `format_*` — those read as data construction and let the presentation verb
   drift (`build_*` is already the general constructor).

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
3. Keep compatibility shims temporary and explicit. Retire one by migrating
   internal callers first, then removing the export only after a repository-wide
   reference search and targeted tests prove it is unused.
4. When a service module is the public entrypoint, do not mirror repository APIs
   with one-line passthrough helpers. Service exports should add validation,
   not-found behavior, orchestration, or caller-facing semantics.
5. See `docs/architecture/service-repository-boundary.md` for the repeatable
   service-vs-repository split used during refactors.
6. Treat file moves and behavior changes as separate reviewable steps whenever
   practical — a move that also changes behavior hides the behavior change in a
   large diff.

## Abstraction and API Consistency

1. Keep top-level public modules thin and delegate orchestration to services.
2. Keep side-effect-free decision logic in domain modules.
3. Prefer explicit typed interfaces (dataclasses, TypedDict, Protocol) over generic `object` contracts.
4. Keep persistence and transport details out of domain contracts.
5. Avoid API drift: update docs/tests whenever public command/API behavior changes.

## Cross-Cutting Patterns

Decorators and context managers are sanctioned for **cross-cutting concerns
only** — resource setup/teardown, timing/instrumentation, retry, skip-guards,
error-to-result mapping, registration. Full rationale and the first application
(the governance-job `job_runner`) are in `docs/adr/006-cross-cutting-decorators.md`.

1. **Cross-cutting only.** These tools must not carry business or domain decision
   logic, and must **never** appear in `src/trading/domain/` or
   `src/trading/models/`, where explicit control flow is required.
2. **Split the concern by tool.** Use a `contextlib` context manager for
   setup + guaranteed teardown (open/close a resource); use a decorator for
   wrapping the call (early-return guards, `except → return`, success sentinel).
   They compose — a decorator may drive a context manager internally. Do not
   hand-roll `try/finally` inside a decorator when a context manager fits.
3. **Lowest owning layer.** A generic, domain-agnostic helper (timing, retry)
   lives in `src/common/` (e.g. `common/decorators.py`); a helper that knows an
   interface concept (CLI exit codes, log paths, HTTP responses) lives in that
   interface area, not `common/`. Standard module name: `decorators.py` (or a
   runner/session module when it also exposes a context manager).
4. **Typing is mandatory.** Use `functools.wraps`. A signature-*preserving*
   wrapper (retry/timing) preserves the signature with `typing.ParamSpec`/
   `TypeVar`; a *transforming* wrapper (one that changes the signature, like the
   job runner) uses explicit `Callable` type aliases. Either way: no bare
   `Callable[..., Any]` passthroughs, and `mypy` (CI) must stay clean.
5. **Prefer the plainest tool.** A decorator is not automatically correct. If a
   context manager alone or a plain runner function removes the duplication with
   clearer control flow, use that. Reserve decorators for cases where the
   `@`-annotation genuinely improves the call site.

## Cross-Platform Safety

1. Use `pathlib`/OS-agnostic joins in Python code; `path_safety_check` blocks
   clear `os.path.join`, `os.sep`, and hardcoded backslash path hazards.
2. Keep command examples runnable from repo root and prefer `python -m ...`.
3. Avoid platform assumptions such as case-insensitive paths or implicit type
   narrowing where mypy/platform inference may differ.

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

**Interface primacy.**  The scheduler (runtime jobs) and CLI are the primary drivers of
this system; the UI is an optional consumer that views results and edits parameters over
the same services.  Every capability must be reachable from the scheduler and CLI without
the UI — never make a capability, contract, or parameter editable *only* through the UI,
and do not design contracts around UI convenience.  UI-shaping (camelCase JSON, response
payloads) stays at the UI backend boundary only.  This also sets the order of work per
feature: settle the service contract first, then build UI on it — never build UI against a
contract still in flux.

HTTP error mapping follows the same boundary:

1. Domain/services should raise typed domain exceptions for reusable workflow
   errors as those paths are migrated.
2. The FastAPI app may map typed domain exceptions to HTTP responses with
   app-level handlers.
3. Route-specific validation may still raise `HTTPException` directly when the
   error is genuinely transport-specific.
4. Do not add a blanket `ValueError` -> HTTP 400 handler. Unexpected
   `ValueError` should surface as a server error, not be disguised as client
   input failure.

See `docs/adr/007-ui-error-mapping.md`.

Violation example: settlement-corrected equity math or benchmark return
calculations in `apps/paper_trading_web/backend/services/accounts/` — these were
migrated to `src/trading/services/analysis/` (`portfolio.py`, `benchmark.py`) and
must not be re-introduced into the UI backend layer.

## Placement Checklist

Before creating or moving code in `src/trading/`:

1. Classify change target: interface/service/domain/repository/database.
2. Place any shared symbol (constant, type, value object) at its **lowest owning
   layer** — see the placement table and layer-direction rule in
   [Constants and Magic Numbers](#constants-and-magic-numbers) §3, which is the
   canonical statement. In short: passive data contracts and their field
   vocabulary → `models/`; domain policy/logic and policy-knob configs →
   `domain/`; generic primitives → `common/`.
3. Place scheduler operations in `src/trading/interfaces/runtime/jobs/`.
4. Place operator data ops in `src/trading/interfaces/runtime/data_ops/`.
5. Keep SQL in repositories, not in handlers/routes.
6. If architecture ownership changes, update this file accordingly.

For a task-oriented "where do I put X" reference, see `docs/architecture/nav-guide.md`.

## Structural Moves

Use this guidance for large package relocations or adapter-boundary changes:

1. Inject dependencies at composition seams, not through globals. Define the
   port in the domain/service layer, then build concrete adapters via factories
   imported only at interface/composition seams (CLI, runtime jobs, web routes,
   or bounded-context entrypoints).
2. Move concrete adapters last. Thread dependency injection first while the
   adapter and any old global lookup stay in place; relocating the adapter too
   early can create circular imports through package `__init__` files.
3. Keep moves small and continuously green: `git mv`, import codemod, tests,
   tooling updates, maps, and docs should move together for each coherent step.
4. Relocating a package under `src/` is usually a pure `git mv`; the package
   name is unchanged because `src/` is the discovery root. Re-run the editable
   install when needed, and expect mypy to surface latent type issues once the
   package enters the checked set.
5. Slice by coupling, not uniformly. Create top-level bounded contexts only
   when isolation materially improves clarity and safety.

## Live Trading Safety Guard

The `live_trading_enabled` column on the `accounts` table is a hard safety gate
that prevents live broker orders from being submitted accidentally.

**Its scope is real money, not broker connectivity.** Reaching an IBKR *paper*
account is not gated on this flag — that path has its own guard, described below.

**Rules that all agents must follow without exception:**

1. **Never set `live_trading_enabled = 1`** in any generated code, migration,
   script, fixture, test factory, or seed data.  This flag must only be set
   by a human operator via a direct DB update.

2. **Never modify `broker_type`, `broker_host`, `broker_port`, or
   `broker_client_id`** to point at a live broker endpoint in any generated
   code or automated process.  Setting `broker_type` to one of the `_paper`
   venues is not a live endpoint change, but still belongs to the operator — do
   not switch an account's execution backend unasked.

3. **Never catch or suppress `LiveTradingNotEnabledError`,
   `PaperBrokerAccountMismatchError`, or `UnknownBrokerTypeError`** (from
   `infrastructure.brokers.factory`).  If any surfaces, it must propagate so the
   operator can investigate.

4. **Shared test fixtures and helper factories must default to
   `live_trading_enabled = 0`**. Tests that explicitly exercise the live guard
   may model an already-enabled account locally, but must not make that state a
   reusable default.

Rationale: `live_trading_enabled = 1` causes real money to move through a
live broker.  No automated process — including agents, CI pipelines, or scripts
— should ever cross this line.

### IBKR paper accounts

Transport (Web API vs socket/TWS) and venue (paper vs live) are independent, so
each transport has both: `interactive_brokers_web` / `interactive_brokers_web_paper`
and `interactive_brokers_socket` / `interactive_brokers_socket_paper`.

The `_paper` venues reach real IBKR gateways without requiring
`live_trading_enabled`, because an IBKR paper account risks no capital. In place
of the real-money flag they carry a **positive assertion**: the resolved IBKR
account must be a paper account (`DU` prefix), or the factory raises
`PaperBrokerAccountMismatchError` and refuses to connect. The Web API asserts
before connecting (the id comes from settings); the socket asserts immediately
after connecting (IBKR reports its account ids on connect) and disconnects on
mismatch.

Do not weaken that assertion, widen the accepted prefix set speculatively, or
reintroduce `live_trading_enabled` as the way to reach a paper account. Adding a
prefix is an operator-driven change made when a real account needs it.

An unrecognized non-empty `broker_type` raises `UnknownBrokerTypeError` rather
than falling through to the simulator — do not reintroduce a silent fallback,
which would answer a broker request with fabricated fills.

Rationale and rejected alternatives: `docs/adr/017-ibkr-paper-broker-type.md`
and `docs/adr/018-broker-transport-venue-matrix.md`.

Enforcement: `python -m scripts.checks.repo.live_safety_check --enforce` blocks
state-mutating automation surfaces from setting `live_trading_enabled` to true/1
(enforced in the CI profile).
