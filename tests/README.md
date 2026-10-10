# Tests

Repository test suite for trading, trends, backtesting, UI backend, and supporting scripts.

## Purpose

Provide reliable verification coverage for runtime behavior, data operations, UI backend flows, and supporting repository scripts.

## Suite Runner

Run focused test groups using `scripts/checks/run_suite.py`. Suite names mirror the `tests/` directory tree and are auto-discovered, so they stay current as the test suite grows.

### List all available suites

```sh
python -m scripts.checks.run_suite --list
```

### Run auto-detected suites (from changed files)

```sh
# Detect suites from uncommitted changes (staged + unstaged)
python -m scripts.checks.run_suite --changed

# Detect suites from all commits on current branch vs main (PR workflow)
python -m scripts.checks.run_suite --base main
python -m scripts.checks.run_suite --base origin/main

# Auto-detect and skip coverage for fast iteration
python -m scripts.checks.run_suite --base main --no-cov
```

The detection maps each changed source file to its deepest matching test suite directory. Documentation-only changes (e.g. `docs/`, `AGENTS.md`) that have no corresponding test suite are silently skipped.

### Run a suite

```sh
# All tests (equivalent to plain pytest)
python -m scripts.checks.run_suite all

# All trading tests
python -m scripts.checks.run_suite trading

# All services
python -m scripts.checks.run_suite src/trading/services

# A single service
python -m scripts.checks.run_suite src/trading/services/market_data
python -m scripts.checks.run_suite src/trading/services/promotion

# Multiple suites combined
python -m scripts.checks.run_suite src/trading/services/market_data src/trading/services/promotion

# Other top-level areas
python -m scripts.checks.run_suite src/backtesting
python -m scripts.checks.run_suite src/trading/repositories
python -m scripts.checks.run_suite src/trading/interfaces
python -m scripts.checks.run_suite apps/paper_trading_web
python -m scripts.checks.run_suite common
```

### Target an individual file

```sh
python -m scripts.checks.run_suite src/trading/services/market_data/test_features.py
```

### Pass extra flags to pytest

```sh
# Verbose, no coverage (fast iteration)
python -m scripts.checks.run_suite src/trading/services -v --no-cov

# Run only tests matching a keyword
python -m scripts.checks.run_suite src/trading/services/market_data -k "test_provider"
```

### Available service suites

| Suite name | Tests directory |
|---|---|
| `src/trading/services` | `tests/src/trading/services/` |
| `src/trading/services/accounts` | `tests/src/trading/services/accounts/` |
| `src/trading/services/analysis` | `tests/src/trading/services/analysis/` |
| `src/trading/services/auto_trading` | `tests/src/trading/services/auto_trading/` |
| `src/trading/services/evaluation` | `tests/src/trading/services/evaluation/` |
| `src/trading/services/autonomy_monitor` | `tests/src/trading/services/autonomy_monitor/` |
| `src/trading/services/market_data` | `tests/src/trading/services/market_data/` |
| `src/trading/services/operational_settings` | `tests/src/trading/services/operational_settings/` |
| `src/trading/services/promotion` | `tests/src/trading/services/promotion/` |
| `src/trading/services/reporting` | `tests/src/trading/services/reporting/` |
| `src/trading/services/books` | `tests/src/trading/services/books/` |

## Quick Start

Run the full suite from the repository root:

```sh
python -m pytest
```

## Commands

Run these from the repository root.

## Targeted Run

```sh
python -m pytest -o addopts= tests/scripts/test_readme_check.py
```

Use `-o addopts=` when local environments do not have coverage plugins required by default pytest options.

## Integration and End-to-End Tests

Two suites break the mirror-`src` layout on purpose, because each test crosses
several modules:

- `tests/integration/` — a flow that crosses several services against a real
  database, with no external process. The `integration` marker.
- `tests/e2e/` — a full workflow driven through a real entrypoint (the CLI or a
  runtime job) against a real database. The `e2e` marker.

The marker follows the folder. `tests/conftest.py` tags every item under those
two paths, so a new file needs no per-module `pytestmark`. Select or exclude a
suite with `-m`:

```sh
python -m pytest -o addopts= tests/integration tests/e2e   # both suites, fast
python -m pytest -m e2e                                     # only e2e
python -m pytest -m "not integration and not e2e"          # only the unit suites
```

Use `-o addopts=` to run these on their own, because the default `addopts`
enforces a repository-wide coverage floor that a subset cannot meet.

**No network, no wall clock.** An e2e test forces the deterministic `demo`
market-data provider (`TRADING_MARKET_DATA_PROVIDER=demo`), so a CLI run makes
no network call and repeats. An integration test that runs the trading runtime
forces the market-hours window open, so it does not depend on when it runs.

### Coverage — anchored on the entrypoint inventory

Scope authority is the **entrypoint inventory** (CLI commands, runtime jobs, API
routes), not the [`docs/overview.md`](../docs/overview.md) narrative. The
overview is an accurate product description, but it compresses the operational
surface — 14 runtime jobs into one bullet, 11 API routes into "an optional web
UI" — so it is the wrong authority for deciding what deserves an integration or
e2e test. Re-derive this inventory from the code when it ages (last derived
2026-09-07); the `overview.md` "Built but not wired up" list carries the same
warning.

The rule these tests follow: integration/e2e covers the **seams unit tests
cannot reach** — CLI parsing, the composition root, the provider factory, cross
-command state, cross-service workflows, and process wiring. Unit tests keep
owning the behavioral matrix and failure branches, so those are not duplicated
here.

**Analytical and trading capabilities**

| Capability | Test |
|---|---|
| Backtesting | `tests/e2e/test_backtest_cli.py` |
| Walk-forward optimization + winner promotion | `tests/e2e/test_backtest_optimize_cli.py` |
| Data-defined strategy variants (CLI write side) | `tests/e2e/test_strategy_variant_cli.py` |
| Data-defined strategy variants (runtime consumption) | `tests/integration/test_variant_drives_trade.py` |
| Signal-driven paper execution + paper trading | `tests/integration/test_paper_trading_run.py` |
| Canonical evaluation → decision score | evaluation unit suite `tests/src/trading/services/evaluation/` + domain `tests/src/trading/domain/test_evaluation_decision_score.py` |
| Promotion workflow (research → paper → live-review) | promotion unit suite `tests/src/trading/services/promotion/` (`test_actions.py` state machine + `test_eligibility.py` approval crossing) |
| Multi-book accounts (independent books share the trade budget) | `tests/integration/test_multi_book_execution.py` |
| Broker abstraction + `live_trading_enabled` guard | unit suite `tests/src/infrastructure/brokers/test_factory.py` + daily-job e2e (real factory, paper path) |
| Feature providers (policy → rotation regime-fit) | `tests/src/infrastructure/feature_providers/test_policy_feature_provider.py` + rotation `test_metrics.py` (composition wiring: daily-job path) |
| Operational settings + parameter source | `tests/src/trading/services/operational_settings/test_mutations.py` + parameters `test_view.py` (mutation→view crossing) |
| Cross-account portfolio risk rollup | `tests/src/trading/services/analysis/test_exposure.py` + `test_concentration.py` (cross-account aggregation) |

**Runtime jobs (14 entrypoints)**

Each job already has a `*_main.py` unit test under
`tests/src/trading/interfaces/runtime/jobs/` (mostly with mocked dependencies).
The e2e tests below prove the real-DB path for one job per family; the rest rely
on their mocked-main unit tests.

| Job family | Real-DB e2e |
|---|---|
| Daily (`run_auto_trades`) | `tests/e2e/test_daily_paper_trading_job.py` |
| Governance weekly (`w1_leaderboard`) | `tests/e2e/test_weekly_governance_job.py` |
| Daily `reconcile_orders` | `tests/e2e/test_reconcile_orders_job.py` |
| Daily `challenger_shadow_eval` / `trader_health` | mocked-main unit tests only |
| Governance `w2` / `w3` / monthly `m1` / `m2` / `m3` | mocked-main unit tests only |
| Maintenance `burn_in_status` / `replay_daily_runs` / `weekly_db_backup` | mocked-main unit tests only |

**API routes (11 modules)**

Every route module has an `api_client` test under
`tests/apps/paper_trading_web/backend/routes/` that runs the real FastAPI app
against a real migrated database — that is integration-level HTTP coverage
already, so these are not re-tested here.

## Fixture Hierarchy

- `tests/conftest.py`: cross-suite fixtures, including `conn` (writable) and `seeded_conn` (read-only seeded DB).
- Suite-level `conftest.py` files provide scoped fixtures for their subtree. Key examples:
  - `tests/src/trading/services/analysis/conftest.py` — `analysis_account`
  - `tests/src/trading/services/evaluation/conftest.py` — `eval_account`
  - `tests/src/trading/services/promotion/conftest.py` — `promotion_account`
  - `tests/src/trading/services/accounts/conftest.py` — `configured_backend`
  - `tests/src/backtesting/conftest.py` — `bt_market_data` factory fixture
  - `tests/src/backtesting/repositories/conftest.py` — `bt_repo_account`, `seed_bt_run`
  - `tests/src/trading/services/market_data/conftest.py` — provider reset per test
  - `tests/apps/paper_trading_web/conftest.py` — `api_client` with isolated DB backend

## Database Fixtures — Which One to Use

**Use `conn`** when the test needs to write data (inserts, updates, deletes). It is function-scoped: each test gets a fresh, empty SQLite DB.

**Use `seeded_conn`** when the test only reads. It is session-scoped and opens the pre-seeded DB read-only (`?mode=ro`). This is faster and does not risk corrupting shared state. The seed covers accounts, trades, snapshots, a book, strategy assignments, daily metrics, backtest runs, and promotion reviews.

Named constants from `tests/support/seed/db.py` (e.g. `ACCT_TREND`, `ACCT_MOMENTUM`, `BOOK_TREND`, `SNAPSHOT_T1`) are the shared vocabulary for referencing seeded entities. Always import and use these constants rather than hard-coding string literals.

## State Isolation

- Database backend is switched to a `tmp_path` SQLite file inside fixtures and restored in a `finally` block.
- `seeded_conn` is enforced read-only at the OS/VFS layer via `?mode=ro` URI flag — not just `PRAGMA query_only`.
- Market data provider environment variables are reset before and after each `tests/src/trading/services/market_data` test.
- Tests that mutate global state should always restore it in fixture teardown.

## Interfaces Layer: `__main__` Entrypoint Tests

`tests/src/trading/interfaces/` tests cover modules that own `if __name__ == "__main__":` blocks — CLI scripts, runtime jobs, and scheduled tasks. These are the only modules in the codebase that are executed directly as processes, so they are the only test files that use `runpy.run_module`.

### The double-import problem

Interface test files typically do two things:

1. **Import the module at top level** so that other tests in the same file can call `module.some_function()` or read `module.SOME_CONSTANT`.
2. **Run the module as `__main__`** in a dedicated entrypoint smoke test to verify the `if __name__ == "__main__":` wiring.

When the module is already in `sys.modules` from step 1, a bare `runpy.run_module(name, run_name="__main__")` triggers a Python `RuntimeWarning`:

```
'trading.interfaces...<module>' found in sys.modules after import of package
'trading.interfaces...', but prior to execution of '...<module>';
this may result in unpredictable behaviour
```

### The fix: `run_module_as_main`

Use `run_module_as_main(module.__name__)` from `loaders.py` instead of calling `runpy.run_module` directly. It temporarily pops the module from `sys.modules`, runs it as `__main__`, then restores it — so subsequent tests in the same worker see the original (monkeypatched) module object:

```python
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    some_module as module,
    run_module_as_main,
)

def test_module_main_entrypoint(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "some_dep", ...)
    run_module_as_main(module.__name__)
```

### When you need this pattern

You need `run_module_as_main` when **both** of these are true:

- The module is imported at the top of the test file (or transitively via `loaders.py`)
- That same module is passed to `runpy.run_module` in a test

All other layers (`services/`, `repositories/`, `domain/`) never have `__main__` entrypoints, so `runpy.run_module` — and therefore this pattern — only appears under `tests/src/trading/interfaces/`.

## UI Backend HTTP Tests

API-route tests under `tests/apps/paper_trading_web/backend/routes/` (via the `api_client` fixture) are the primary HTTP coverage surface for the web backend.

Historical caveat: a past regression sweep hit hangs in the **synchronous FastAPI route-dispatch path** that reproduced even for a minimal app and even through `httpx.ASGITransport` (a minimal *async* app worked). The takeaway if HTTP-style hangs ever resurface: the cause is environmental sync-route execution, not Starlette's `TestClient` alone — investigate that rather than rewriting the shared `api_client` fixture, since a fixture-level workaround would spread a bad assumption across the whole UI backend suite.

## Audit Notes

- Full repository validation remains `python -m pytest` from repo root.
- Cross-stack smoke validation is `python -m scripts.run_checks ci`.
- For parser/default-path changes, include focused checks for CLI parser/handler coverage under `tests/src/trading/interfaces/cli/` and runtime-job coverage under `tests/src/trading/interfaces/runtime/jobs/`.

## Test Support Layout

`tests/support/` holds shared test utilities used across multiple test suites.

```
tests/support/
  seed/                    # DB population helpers (session-scoped shared DB)
    db.py                  # orchestrator — called by tests/conftest.py
    accounts.py, backtesting.py, promotion_review.py,
    reporting.py, book_data.py
  cli/                     # CLI test infrastructure
    backtesting.py, main.py
  account_records.py       # make_account_record() — used everywhere
  accounts.py              # make_accounts_service_row()
  analysis.py              # make_analysis_account(), record_analysis_buy(), patch_analysis_market_data()
  backtesting.py           # make_backtest_config(), install_backtest_market_data(), etc.
  brokers.py               # make_broker_account(), make_broker_order()
  evaluation.py            # insert_backtest_run(), insert_backtest_snapshot(), etc.
  promotion.py             # make_ready_evaluation(), make_observing_assessment()
  reporting.py             # insert_trade(), insert_snapshot(), make_evaluation_artifact()
  repositories.py          # insert_repository_account()
  books.py               # insert_test_book(), build_book_env()
```

Helpers that are exclusively used by a single suite live co-located with that suite rather than in `tests/support/`:

- `tests/src/trading/interfaces/runtime/jobs/loaders.py` — runtime job module loaders and `run_module_as_main` (see [Interfaces Layer: `__main__` Entrypoint Tests](#interfaces-layer-__main__-entrypoint-tests))
- `tests/src/trading/services/auto_trading/factories.py` — auto-trading fakes and builders
- `tests/src/trading/services/accounts/seed.py` — admin dataset seeding

**Convention:** if a co-located `factories.py` is imported from outside its own directory, move it to `tests/support/` under a domain-based name.
