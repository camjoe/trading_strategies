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

> **Status: A DONE (mechanical)** — codemod rewrote 395 path refs across ~40 docs;
> `link_check` real residuals = 0 (remaining broken refs are forward-looking
> targets inside these restructure docs). `architecture-conventions.md` ownership
> map + dependency rules now read `src/trading/` and `src/infrastructure/`.
> **Carve-out:** `docs/maps/trading-package-map.md` needs a content regeneration
> (drop the now-misplaced `database` section, document the 152 current files) —
> that's an `update-documentation` skill task, advisory, tracked separately.

### A2 — Clear the mechanical doc-link drift (one consolidated pass)
- Running after Group 0 lets this clear **all** path relocations at once. Apply across all docs (codemod or scripted):
  - `trading/{domain,interfaces,models,repositories,services}/` → `src/trading/...` (from Group 0)
  - `trading/database/` → `src/infrastructure/database/`
  - `trading/backtesting/` → `src/trading/backtesting/`
  - `tests/brokers/` → `tests/src/infrastructure/brokers/`
- Regenerate/patch `docs/maps/trading-package-map.md` and `docs-map.md`.
- **DoD:** `python -m scripts.checks.link_check` and `maps_check` clean (or only unrelated residue, recorded).

---

## Group B — Extract the market-data adapter to infrastructure

This is the one genuine refactor in the phase (not just a move): the `yfinance`
adapter must land in `src/infrastructure/market_data/` **without** `trading/`
importing `infrastructure/`. It mirrors the existing brokers pattern (port in
domain, adapter + factory in infrastructure, wired at the interface/composition
layer). The existing `get_provider`/`set_provider` seam (registry.py:114-126) is
the foundation to build on.

**End state:**
- `trading/.../market_data/protocols.py` — the **ports** (`MarketDataProvider`, `FeatureDataProvider` ABCs). Stays in the domain.
- `trading/.../market_data/runtime.py` — the **holder**: `get_provider()/set_provider()/set_provider_by_name()` over a module-global typed as the port. No concrete imports, no import-time concrete default.
- `src/infrastructure/market_data/providers.py` — `YFinanceProvider`, `UnavailableProvider` (imports `yfinance`; imports the port from trading — infra→domain is allowed).
- `src/infrastructure/market_data/factory.py` — the `_PROVIDER_FACTORIES` name→class map + config/env resolution (`TRADING_MARKET_DATA_PROVIDER`, config file). Exposes `install_configured_provider()` that calls `set_provider(...)`.
- Composition roots (CLI `main`, web app startup, runtime job runners, backtest entry) call `install_configured_provider()` once at startup.

### B1 — Split holder from factory, in place (no move yet)
- Within `trading/.../market_data/`, separate `registry.py` into: a **holder** (`runtime.py`: get/set state, port-typed, no concrete imports) and the **factory** (keep temporarily as `_factory.py`, still importing concrete `providers.py`).
- Replace the import-time concrete default with an explicit `install_configured_provider()` call; have the package `__init__` (or a temporary shim) call it so behavior is unchanged this commit.
- **Gotcha:** preserve current "just works on import" behavior here so this commit is a pure internal refactor with all tests green. Drop the implicit default only in B2.
- **DoD:** no public API change; `market_data` tests green.

### B2 — Move the adapter + factory to infrastructure; wire composition
- `git mv` concrete `providers.py` and `_factory.py` → `src/infrastructure/market_data/`. Rename `_factory.py` → `factory.py`.
- Repoint the factory's port import to `trading.…market_data.protocols` (infra→domain, allowed).
- Remove the implicit import-time default from `trading`; add `install_configured_provider()` calls at the composition roots (CLI main, web app lifespan/startup, job runners, backtest setup).
- Drop the `YFinanceProvider`/`yf` re-exports from `trading/.../market_data/__init__.py`.
- **Add a layer rule** (slice-aware or simple): `trading/**` must not import `infrastructure.market_data.` — parallel to the brokers/feature_providers rules. Add a unit test for it.
- Codemod the few concrete-class import sites (package `__init__`, registry).
- **Gotcha:** anything that previously relied on the import-time provider now needs an explicit install — that's the call-site work; CI will surface any entrypoint that forgot.
- **DoD:** layer check enforces the new boundary; `run_checks --profile quick` green.

### B3 — Relocate market-data provider tests
- `git mv tests/trading/services/market_data/test_providers.py` and `test_registry.py` → `tests/src/infrastructure/market_data/`, adjusting to the new import paths and to **install/inject a provider** rather than relying on the old import-time default (use `set_provider(fake)` in fixtures).
- Add `__init__.py` through the new `tests/src/infrastructure/market_data/` chain.
- **DoD:** market-data tests green at the new location; coverage still reports the adapter.

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
