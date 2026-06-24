# Foundation Phase — Commit Plan

Type: runbook
Status: Draft
Created: 2026-06-22
Last Reviewed: 2026-06-22
Purpose: Concrete, ordered commit list for the foundation phase — clean up top-level boundaries and finish separating infrastructure, BEFORE any domain-slicing. Each commit follows the per-move checklist in [migration-runbook.md](migration-runbook.md) and ends green.
Related: [Target Structure](target-structure.md), [Migration Runbook](migration-runbook.md)

## Goal

Deliver the boundary cleanup that was the real motivation: a clean
`src/{trading, infrastructure, common}` + `apps/` base with infrastructure
genuinely separated from the trading domain. This is ~6–8 small commits and is
independent of (and prerequisite to) any later domain slicing.

Every commit: `git mv` where files move, codemod imports, update tooling/docs in
the same commit, finish with `python -m scripts.run_checks --profile quick` green.

---

## Group 0 — Relocate `trading/` → `src/trading/` (do this FIRST)

> **Status: 0a + 0b DONE** — package relocated (`550a13d`), tests relocated to
> `tests/src/trading/` with the `tests.trading` → `tests.src.trading` codemod and
> the `tests/src` `__init__.py` chain completed. `run_checks --profile quick` green
> (1952 passed, 98.13% cov). **Group A (reconcile docs) next.**

`trading` is currently a **split namespace package** (root `trading/` +
`src/trading/backtesting/`), which forces dual-path tooling (two `--cov` entries,
split layer globs, `trading`+`src` targets). Consolidating it first removes that
tax and gives every later step a single `src/trading` root.

**Why it's cheap:** moving the package does **not** change import paths — code
imports `trading.X` whether the package sits at root or under `src/` (it's the
package *name*; `src/` is already on `sys.path` via the editable install).
`trading.__path__` already merges both roots. So this is a **pure `git mv`** with
**no import rewrites** — the codemod that makes other moves expensive does not
apply here. No collision: `src/trading/` holds only `backtesting/` today.

### 0a — Move the package
- `git mv` root `trading/{domain,interfaces,models,repositories,services}` (and any
  loose modules) into `src/trading/` (merging alongside the existing `backtesting/`).
- Update **path-based** tooling (not imports) in the same commit:
  - `layer_check.py`: prefix every `trading/...` `source_glob` and the
    `runtime_loader.py` exception path with `src/`.
  - `ruff_check.py` / `mypy_check.py`: drop the `"trading"` target (now covered by `"src"`).
  - `pytest.ini`: collapse `--cov=trading --cov=src/trading` → `--cov=trading`
    (now single-path).
  - `link_check.py` / `maps_check.py`: repoint scanned `trading/...` paths.
- **`common/paths/project_paths.py`:** leave `TRADING_DIR`, `LEGACY_ACCOUNT_PROFILES_*`
  **as-is** — they are frozen back-compat *data* references, not package paths
  (verified: `trading/account_profiles/` doesn't exist; used only by
  `trading/services/profiles/source.py`). Optional clarity fix: rename
  `TRADING_DIR` → `LEGACY_TRADING_DIR` so nobody later "corrects" it to `src/`.
- **DoD:** `run_checks --profile quick` green. (Risk is low precisely because
  imports don't move — any failure points at an exact path-tooling miss.)

### 0b — Move the tests
- `git mv tests/trading/` → `tests/src/trading/` (also pure `git mv`, no import
  changes), adding `__init__.py` through the `tests/src` / `tests/src/trading` chain.
- **DoD:** full suite green at the new locations; coverage unchanged.

> After Group 0, root `trading/` is gone and everything trading-related lives under
> `src/trading`. Groups A and B below then operate entirely within `src/`.

---

## Group A — Reconcile the already-done moves (trust the foundation)

### A1 — Fix architecture docs for the database + backtesting moves
- `architecture-conventions.md`: Ownership Map #6 `trading/database/` → `src/infrastructure/database/`; #8 `trading/backtesting/` → `src/trading/backtesting/`; update Allowed/Disallowed dependency examples that name `trading/database`.
- Fix the stale docstring `trading.database.config.get_db_path` in `src/infrastructure/database/backend.py`.
- (Layer check rules already repointed — done in a prior commit.)
- **DoD:** docs match reality; `run_checks --profile quick` green.

> **Status: A DONE** — codemod rewrote ~395 path refs across ~40 docs (`b8968ca`);
> `architecture-conventions.md` ownership map + dependency rules now read
> `src/trading/` and `src/infrastructure/`. Follow-up `d987079` fixed two CHECKER
> bugs that the move exposed (not real drift): `maps_check` KNOWN_TOP_DIRS lacked
> `src` (double-prefixed every `src/...` token → false "152 undocumented/158
> stale"); `link_check` now skips the restructure planning docs (forward-looking
> paths) and 4 README relative links were re-depthed. **All CI doc checks pass:
> link_check 0 broken, maps_check in sync, db_schema pass.** No map content
> regeneration was needed.

### A2 — Clear the mechanical doc-link drift (one consolidated pass)
- Running after Group 0 lets this clear **all** path relocations at once. Apply across all docs (codemod or scripted):
  - `trading/{domain,interfaces,models,repositories,services}/` → `src/trading/...` (from Group 0)
  - `trading/database/` → `src/infrastructure/database/`
  - `trading/backtesting/` → `src/trading/backtesting/`
  - `tests/brokers/` → `tests/src/infrastructure/brokers/`
- Regenerate/patch `docs/maps/trading-package-map.md` and `docs-map.md`.
- **DoD:** `python -m scripts.checks.link_check` and `maps_check` clean (or only unrelated residue, recorded).

---

## Group B — Extract the market-data adapter to infrastructure (full DI)

Approach (ratified): **full dependency injection**, mirroring the brokers pattern
(`broker_factory` callable injected from the interface layer into services). The
`MarketDataProvider` flows from composition roots down to the 6 consumers; the
global `get_provider()` locator is removed in the end state.

**Critical ordering lesson (learned the hard way):** the concrete adapter
(`providers.py`) must move to `infrastructure` **LAST**. Moving it first creates a
circular import — `infrastructure.market_data.providers` imports
`trading.services.market_data.cache`, which triggers trading's package `__init__`,
which (via `registry.py` / re-exports) imports back into the partially-initialized
`infrastructure.market_data.providers`. So: thread DI while the concrete adapter
**and** the global registry stay in `trading`, and only relocate the concrete once
nothing in `trading` constructs it.

**Consumers to inject** (6 `get_provider()` + 1 `get_feature_provider()` site):
`pricing/lookups`, `reporting/benchmark`, `auto_trading/market`,
`backtesting/services/backtest_data_service`, `backtesting/services/execution_service`
(feature provider), `apps/trends/data`.

> **Status: B1 + B2 COMPLETE.** B1 made every consumer injectable; B2 wired the
> composition roots and **deleted the global locator**:
> - B2a (`d4fef8c`) — added stateless `factory.py` builders
>   (`build_provider`/`build_feature_provider`/`supported_provider_names`).
> - B2b (`0bea8bf`) — trends + backtest seam build via the builders.
> - B2c-1 (`67ea41b`) — provider injected through reporting/analysis chains + roots
>   (CLI reporting deps via `partial`, web routes per-request).
> - B2c-2 (`03f71aa`) — provider injected through the auto_trading + rotation chain
>   from the `run_auto_trades` job root.
> - B2d (`4fa05aa`) — deleted `registry.py` (get/set_provider, feature-provider
>   globals, config hot-reload, import-time YFinanceProvider default); leaves now
>   call `require_provider`/`require_feature_provider` guards. No `get_provider()`
>   references remain in `trading`. Quick gate green throughout (1955 passed).
>
> Note: composition roots resolve the provider per entry (web routes build one per
> request; the FastAPI `Depends` form in the B2 sketch below was not needed). The
> test-double churn the plan anticipated landed in B2c–B2d.
> **Next: B3** — move concrete adapter + factory to `src/infrastructure/market_data`,
> add the `src/trading ↛ infrastructure.market_data` layer rule (the actual goal).

### B1 — Thread DI area-by-area (concrete + registry stay in `trading`)
One green commit per area; during this stage composition roots get the provider
from the existing `get_provider()` bridge (so behavior is unchanged):
- **B1a — backtesting**: add `provider`/`feature_provider` params to
  `backtest_data_service` + `execution_service`; thread up through
  `leaderboard_service`/`report_service`/`backtesting.__init__` to the backtest
  entry points (web route `api_run_backtest`, CLI backtest commands, backtest jobs).
- **B1b — pricing**: `fetch_latest_prices`/`benchmark_stats` ← thread through
  `analysis/queries`, `auto_trading/inputs`/`rotation`, `reporting`.
- **B1c — reporting**: `fetch_benchmark_close_history`/`build_live_benchmark_overlay`
  ← thread through the web `accounts` route/services.
- **B1d — auto_trading**: `build_iv_rank_proxy` ← `auto_trading/inputs`.
- **B1e — feature provider**: inject the `FeatureDataProvider` into
  `ProxyFeatureDataProvider.build_feature_bundle` / `execution_service` (it's a
  second global, `get_feature_provider()`).
- **DoD each:** that area no longer calls `get_provider()`/`get_feature_provider()`; `run_checks --profile quick` green.

### B2 — Wire composition roots; remove the global locator
- Web app: provide the `MarketDataProvider` via FastAPI `Depends`. CLI / runtime
  jobs / backtest entry / `trends`: construct once at entry and inject down.
- Delete `get_provider`/`set_provider`/`registry` globals from `trading` once no
  consumer references them.
- **DoD:** no `get_provider()` references remain; gate green.

### B3 — Relocate the concrete adapter + factory (now safe — no cycle) — **DONE (`b6126e3`)**
- `git mv providers.py` → `src/infrastructure/market_data/providers.py` (imports the
  `MarketDataProvider` port + transport cache from `trading.services.market_data`).
- New `src/infrastructure/market_data/factory.py` owns `build_provider(name=None)` +
  `_PROVIDER_FACTORIES` + env/config resolution + `supported_provider_names`. The
  trading-side `factory.py` keeps only `build_feature_provider` (ProxyFeatureDataProvider
  has no external dep, stays in trading).
- Composition seams import `infrastructure.market_data.factory.build_provider`:
  CLI main, run_auto_trades job, backtest seam, web routes, trends.
- Layer rule added: `src/trading ↛ infrastructure.market_data.` (exceptions: the CLI,
  run_auto_trades, and backtest seams) + unit tests; enforced by `layer_check.py`.
- `git mv test_providers.py` → `tests/src/infrastructure/market_data/`; factory/build_provider
  tests split there too (+ `__init__`/conftest chain); `yf` patches repoint to infrastructure.
- architecture-conventions.md ownership map documents the new package (#12).
- **DoD met:** layer check enforces the boundary; quick gate green (1957 passed);
  coverage still reports the adapter under `--cov=src/infrastructure`.

> **Group B COMPLETE.** Infrastructure is now genuinely separated from the trading
> domain — the yfinance dependency lives only in `src/infrastructure/market_data/`,
> wired at composition seams. Stop-and-reassess point reached (see Order & checkpoints).

### B4 (optional) — Evaluate `cache.py`
- Decide if `market_data/cache.py` is transport-level caching (→ infrastructure) or domain-object caching (→ stays). Move only if the former. Skip if ambiguous.

---

## Group C — Shared kernel & apps (decisions; can defer)

### C1 (optional) — `common/` → `src/common/`
- `common/` already functions as the shared kernel (112 importers). Relocating it to `src/common/` buys sibling-consistency with `src/trading` + `src/infrastructure` (the three-sibling base). Like Group 0 it's a **pure `git mv`** — `common.X` imports are unchanged since `src/` is on the path. Best done right after Group 0 (when the three-sibling shape becomes real), or skipped if you'd rather keep `common/` at root. Adds nothing functional either way.

### C2 (optional) — `apps/trends` tickers duplication
- `trends/tickers.py` likely duplicates `common/tickers.py`. Decide: either point `trends` at `common/` (dedupe), or keep `trends` deliberately isolated as a standalone tool. No action required for the boundary itself — `trends` already shares no code with the trading system.

---

## Order & checkpoints

1. **Group 0 (0a → 0b)** — relocate `trading/` → `src/trading/` + tests. Pure `git mv`; collapses the dual-path tooling. Single consistent `src/` base for everything after.
2. **A1 → A2** — reconcile conventions/docs; A2 folds the `trading/ → src/trading/` path drift into one pass with the database/backtesting/brokers relocations.
3. **B1 → B2 → B3** — market-data extraction (the careful part), now entirely within `src/`.
4. Reassess. C1 (`common → src/common`) can ride right after Group 0; C2 optional.

**Stop-and-reassess point:** after Group B, the "infrastructure separated, clean
top-level bounds" goal is essentially met. That is the natural moment to decide
whether domain slicing (e.g. evaluating more `sleeves`-like contexts) is worth
pursuing as a separate effort.
