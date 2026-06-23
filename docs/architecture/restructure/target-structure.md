# Target Package Structure (src/ restructure)

Type: architecture
Status: Draft
Created: 2026-06-22
Last Reviewed: 2026-06-22
Purpose: Define the target vertical-slice architecture for `src/trading/` and the cross-cutting rules that govern the migration. This is the authoritative "what we are building toward" document; the step-by-step execution lives in [migration-runbook.md](migration-runbook.md).
Related: [Architecture Conventions](../architecture-conventions.md), [Migration Runbook](migration-runbook.md), [Trading Package Map](../../maps/trading-package-map.md)

## Why this change

Move from **layer-first** (`trading/services/`, `trading/repositories/`, `trading/domain/`, `trading/models/`) to **feature-first vertical slices** with layering *inside* each large slice — the shape Sleeves already proved out. Goal: cohesion (a feature's code lives together), findability, and the option to extract a slice later.

## Core principles

1. **Vertical slices at the top level.** Each business domain is a top-level package under `src/trading/`.
2. **Layered inside *large* slices, flat inside *small* ones.** A large slice has `domain/ models/ repositories/ services/`. A small slice is a flat set of modules. Promote a slice from flat → layered only when it grows past a few modules.
3. **`infrastructure/` is a sibling of `trading/`, never nested under it.** It is shared by the web app and scripts (see [Hard constraints](#hard-constraints)).
4. **Drop redundant prefixes.** The package namespaces the module — `accounts/models/config.py`, not `accounts/models/account_config.py`.
5. **No stutter paths.** Avoid `promotion/repositories/promotion.py`. Use a flat `promotion/repository.py` for a single-module layer; promote to a `repositories/` directory only when it splits into multiple files.
6. **One consistent place for models.** `models/` is its own layer in every layered slice (not sometimes under `domain/`). Data shapes (`*Config`/`*Insert`/`*Record`/`*State`) are distinct from policy/math in `domain/`.

## Target tree

```
src/
├── trading/
│   ├── accounts/            # layered
│   ├── sleeves/             # layered (reference implementation)
│   ├── promotion/           # layered
│   ├── evaluation/          # layered
│   ├── backtesting/         # layered — already migrated, leave as-is
│   ├── reporting/           # flat
│   ├── market_data/         # flat + providers/ subdir
│   ├── profiles/            # shape TBD
│   ├── universe/            # shape TBD
│   ├── analysis/            # shape TBD
│   ├── admin/               # shape TBD
│   ├── auto_trading/        # layered (D1b)
│   ├── ibkr_paper_monitor/  # flat (D1d)
│   ├── runtime/             # service slice: services/{settings,throttle} (D2)
│   ├── interfaces/          # cli/ + runtime/jobs/ only — no api/ (D3)
│   └── shared/              # cross-slice contracts, constants, exceptions
│   #  accounting → accounts/ (D1a) · pricing → market_data/ (D1c) · no src/trading/config (D5)
│
├── infrastructure/          # SIBLING of trading — adapters to the outside world
│   ├── database/
│   ├── brokers/             # ib_async adapter + factory
│   ├── feature_providers/   # external alt-data adapters (praw, pytrends, ...)
│   ├── market_data/         # external market-data adapter (yfinance) — TO MOVE
│   └── config/              # file-backed static config assets
│
├── common/                  # SIBLING — shared kernel (constants, paths, time,
│                            #   coercion, tickers); imported by trading/app/scripts
│
apps/
├── paper_trading_web/       # web API surface — stays here
└── trends/                  # standalone tool — no shared imports (see note below)
```

## Internal shape of a layered slice

```
<slice>/
├── domain/          # pure policy / decision / math — no DB, IO, or network
├── models/          # data shapes: *Config / *Insert / *Record / *State
├── repositories/    # SQL persistence adapters
├── services/        # orchestration: compose domain + repositories
└── __init__.py
```

`interfaces` (CLI/runtime/API) stays a cross-cutting layer at `src/trading/interfaces/`, not duplicated inside each slice.

## Foundation: infrastructure separation (do first)

The original pain was top-level mess and infrastructure tangled inside `trading/`,
not the internal shape of domains. This phase fixes the *boundaries* and is the
highest-value, lowest-risk work. The rule is **ports & adapters**:

- A **port** (a `Protocol`/`ABC` contract) stays in the domain (`trading/` or `shared/`).
- An **adapter** (concrete code that imports an external lib or does IO) lives in `src/infrastructure/`.

Audit findings (from the current import graph):

| Item | Verdict |
|---|---|
| `trading/services/market_data/providers.py` imports **`yfinance`** | **MOVE** the adapter to `src/infrastructure/market_data/`. Keep the port `market_data/protocols.py` (`MarketDataProvider(ABC)`) in the domain; the registry/factory is the wiring seam. This is the one real remaining infra leak — the exact peer of `brokers`/`feature_providers`, which are already isolated. |
| `trading/services/market_data/cache.py` | **Evaluate** — storage/caching leans infrastructural; move only if it caches at the transport boundary, keep if it caches domain objects. |
| `sqlite3` imports across `trading/services/**` | **Keep** — confirmed type-hints only (`sqlite3.connect` count = 0 in services); the DB boundary is already clean via repositories. |
| `trading/services/pricing/` | **Keep in domain** — consumes the market-data *port*, no external IO of its own (folds into `market_data/` per D1c). |
| `database`, `brokers`, `feature_providers`, `config` | Already in `src/infrastructure/` — validate enforcement/docs only. |

Shared kernel & apps:

- **`common/` is genuinely shared** (imported by trading 70, scripts 21, src 15, apps 6) — keep it a top-level sibling, not under `trading/`. When `trading/` moves under `src/`, place `common/` at `src/common/` alongside `src/trading` and `src/infrastructure` for a consistent three-sibling base.
- **`apps/trends` is fully standalone** (no shared imports). No entanglement to fix; the boundary is already clean. Only nit: `trends/tickers.py` likely duplicates `common/tickers.py` — decide whether `trends` should depend on `common/` or stay deliberately isolated as a separate tool.

## Cross-slice dependency rules

These are the rules that keep vertical slices from degrading into a tangle. **They must be enforced by the layer check, not just documented.**

1. A slice may import: its own internals, `src/trading/shared/`, `src/infrastructure/`, and `common/`.
2. A slice **must not** import another slice's internal `domain/`, `models/`, or `repositories/`.
3. Cross-slice collaboration goes through **one** of:
   - a shared contract in `src/trading/shared/`, or
   - the other slice's `services/` public entry points (the slice's "front door").
4. Within a slice, the layering rule still holds: `services → repositories/domain`; `domain` imports nothing below itself; `interfaces → services` only.
5. `interfaces/` is the sole wiring point for `infrastructure/` adapters (brokers, providers) — slices never import broker/provider SDKs directly. (Carried over from current conventions.)

What seeds `shared/`: cross-slice contracts that exist today in `trading/domain/` — e.g. `feature_provider.py`, `broker_connection.py`, `exceptions.py`, and cross-module constants.

## Hard constraints (do not violate)

- **`infrastructure/` stays at `src/infrastructure/`.** It is imported by `apps/paper_trading_web/backend/services/db.py` and by `scripts/` (`db_schema_check`, `describe_db_schema`, `ibkr_web_api_smoke_test`). Nesting it under `trading/` would couple the web app and scripts to the trading package and undo the editable-install setup.
- **The web backend (`apps/paper_trading_web`) remains transport-only** and must not absorb domain logic during the move (existing UI Backend Boundary Rule).
- **Live-trading safety guards are untouched** by any move (existing rule).

## Decisions D1–D5 (ratified 2026-06-22)

| # | Decision | Resolution |
|---|---|---|
| D1a | Home for `accounting` (2 modules: mutations, queries) | **Fold into `accounts/`** (`accounts/services/accounting.*`). Verified not used by `sleeves`. It *is* a cross-cutting ledger service imported by `analysis`, `auto_trading` (3×), `reporting`, the web app, and the CLI — so `accounts/` is a deliberately core slice; those consumers import its `services/` **front door** (allowed by cross-slice rule 3), never its internals. |
| D1b | Home for `auto_trading` (10 modules + `domain/auto_trading_policy.py`) | Its own **layered slice `auto_trading/`**. Its many `runtime_*` modules couple it to `runtime` (see D2); jobs call into it. |
| D1c | Home for `pricing` (1 module: lookups) | **Fold into `market_data/`** (`market_data/pricing.py`). |
| D1d | Home for `ibkr_paper_monitor` (2 modules) | Its own **flat slice `ibkr_paper_monitor/`** (distinct broker-monitoring/operational concern). |
| D2 | `runtime/` shape | **Split, don't merge.** `interfaces/runtime/jobs/` stays in the **interface** layer (scheduler entrypoints: `run_auto_trades`, `scheduler_installer`, daily/governance/maintenance). `runtime_settings` + `runtime_throttle` become a **`runtime/` service slice** (`runtime/services/{settings,throttle}`, `runtime/models.py`). Jobs call the runtime slice + `auto_trading`; they are not part of it. |
| D3 | `interfaces/api/` vs `apps/paper_trading_web` | **No second API surface.** `apps/paper_trading_web` stays the sole HTTP API. `src/trading/interfaces/` holds only `cli/` and `runtime/`. Drop `api/` from the target tree. |
| D4 | `models/` convention | **`models/` is its own layer** in every layered slice (data shapes distinct from `domain/` policy). |
| D5 | `src/trading/config/` vs `src/infrastructure/config/` | **Drop `src/trading/config/`.** Keep `src/infrastructure/config/` for file-backed static assets; put cross-cutting constants in `src/trading/shared/` and the existing `common/constants.py`. |

### `shared/` seed list

Move these cross-slice contracts from `trading/domain/` into `src/trading/shared/`
during the foundation phase (importer counts from current code):
`feature_provider` (11), `broker_connection` (7), `exceptions` (5), `returns` (5).
`indicators_adapter` (1 importer) stays with its consumer unless it grows.

### Sequencing principle

Foundation first: `infrastructure/` + `shared/`/`common/` are moved and validated
**before** any `src/trading/` business slice, so slices build on a proven base.
See the runbook's [Order of moves](migration-runbook.md#order-of-moves).

## Slice inventory & source mapping

Status: `done` = already moved · `ready` = mapped, shape agreed · `proposed` = shape needs confirming · `decision` = see Open decisions.

| Slice | Current source location(s) | Internal shape | Status |
|---|---|---|---|
| backtesting | `src/trading/backtesting/` | layered | done |
| accounts | `domain/accounting.py`, `models/account_*.py`, `repositories/accounts.py`, `services/accounts/` | layered | ready |
| sleeves | `domain/sleeve_*.py`, `models/sleeve_*.py`, `repositories/sleeve*.py`, `services/sleeves/` | layered | ready |
| promotion | `domain/promotion_*.py`, `repositories/promotion.py`, `services/promotion/` | layered | ready |
| evaluation | `domain/evaluation_*.py`, `services/evaluation/` | layered | ready |
| reporting | `services/reporting/` | flat | proposed |
| market_data | `services/market_data/` | flat + `providers/` | proposed |
| profiles | `services/profiles/` | TBD | proposed |
| universe | `services/universe/` | TBD | proposed |
| analysis | `services/analysis/` | TBD | proposed |
| admin | `services/admin/`, `repositories/admin.py` | TBD | proposed |
| accounting | `services/accounting/` | → folds into `accounts/services/` | ready (D1a) |
| auto_trading | `domain/auto_trading_policy.py`, `services/auto_trading/` | layered | ready (D1b) |
| pricing | `services/pricing/` | → folds into `market_data/` | ready (D1c) |
| ibkr_paper_monitor | `services/ibkr_paper_monitor/` | flat | ready (D1d) |
| runtime | `services/runtime_settings/` + `services/runtime_throttle/` (jobs stay in `interfaces/`) | service slice: `services/{settings,throttle}`, `models.py` | ready (D2) |
| interfaces | `interfaces/cli/`, `interfaces/runtime/jobs/` | cross-cutting (cli + runtime jobs only) | ready (D2/D3) |

> Note: this table is a planning aid. The authoritative, file-level move list is `FILE_MOVES.csv` (generated once the open decisions are closed).

## Tooling impact (must move with the code)

The layer check is the biggest engineering item: [scripts/checks/layer_check.py](../../../scripts/checks/layer_check.py) expresses rules as flat import-prefix matches (`trading/services/**` may not import `trading.database.`). Vertical slicing moves the layer name into the *middle* of the dotted path (`trading.accounts.repositories.accounts`), which the current matcher cannot express. It needs a slice-aware matcher (layer segment anywhere in the path) **before** the first layered slice moves. See the runbook for the full per-move tooling/doc checklist.
