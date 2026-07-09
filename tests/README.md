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
python -m scripts.checks.run_suite src/trading/backtesting
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
| `src/trading/services/accounting` | `tests/src/trading/services/accounting/` |
| `src/trading/services/accounts` | `tests/src/trading/services/accounts/` |
| `src/trading/services/admin` | `tests/src/trading/services/admin/` |
| `src/trading/services/analysis` | `tests/src/trading/services/analysis/` |
| `src/trading/services/auto_trading` | `tests/src/trading/services/auto_trading/` |
| `src/trading/services/evaluation` | `tests/src/trading/services/evaluation/` |
| `src/trading/services/ibkr_paper_monitor` | `tests/src/trading/services/ibkr_paper_monitor/` |
| `src/trading/services/market_data` | `tests/src/trading/services/market_data/` |
| `src/trading/services/operational_settings` | `tests/src/trading/services/operational_settings/` |
| `src/trading/services/pricing` | `tests/src/trading/services/pricing/` |
| `src/trading/services/profiles` | `tests/src/trading/services/profiles/` |
| `src/trading/services/promotion` | `tests/src/trading/services/promotion/` |
| `src/trading/services/reporting` | `tests/src/trading/services/reporting/` |
| `src/trading/services/books` | `tests/src/trading/services/books/` |
| `src/trading/services/universe` | `tests/src/trading/services/universe/` |

### Targeted runs in GitHub Actions

Use the **Targeted Tests** workflow (`targeted-tests.yml`) for focused validation on a branch without waiting for the full CI suite:

```sh
gh workflow run targeted-tests.yml --ref <your-branch> -f suites="src/trading/services/market_data"
gh workflow run targeted-tests.yml --ref <your-branch> -f suites="src/trading/services/market_data,src/trading/services/promotion"
gh workflow run targeted-tests.yml --ref <your-branch> -f suites="all" -f extra_args="--no-cov"
```

The workflow accepts a `suites` input (space- or comma-separated suite names) and an optional `extra_args` input for additional pytest flags.

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

## Daily Snapshot Tests

Daily snapshot scheduler coverage lives in:

- `tests/src/trading/interfaces/runtime/jobs/daily/test_daily_snapshot_helpers.py`
- `tests/src/trading/interfaces/runtime/jobs/daily/test_daily_snapshot_main.py`

Run only this test slice:

```sh
python -m scripts.checks.run_suite src/trading/interfaces/runtime/jobs/daily
```

## Fixture Hierarchy

- `tests/conftest.py`: cross-suite fixtures, including `conn` (writable) and `seeded_conn` (read-only seeded DB).
- Suite-level `conftest.py` files provide scoped fixtures for their subtree. Key examples:
  - `tests/src/trading/services/analysis/conftest.py` — `analysis_account`
  - `tests/src/trading/services/evaluation/conftest.py` — `eval_account`
  - `tests/src/trading/services/promotion/conftest.py` — `promotion_account`
  - `tests/src/trading/services/admin/conftest.py` — `configured_backend`
  - `tests/src/trading/backtesting/conftest.py` — `bt_market_data` factory fixture
  - `tests/src/trading/backtesting/repositories/conftest.py` — `bt_repo_account`, `seed_bt_run`
  - `tests/src/trading/services/market_data/conftest.py` — provider reset per test
  - `tests/apps/paper_trading_web/conftest.py` — `api_client` with isolated DB backend

## Database Fixtures — Which One to Use

**Use `conn`** when the test needs to write data (inserts, updates, deletes). It is function-scoped: each test gets a fresh, empty SQLite DB.

**Use `seeded_conn`** when the test only reads. It is session-scoped and opens the pre-seeded DB read-only (`?mode=ro`). This is faster and does not risk corrupting shared state. The seed covers accounts, trades, snapshots, a sleeve, strategy assignments, daily metrics, backtest runs, and promotion reviews.

Named constants from `tests/support/seed/db.py` (e.g. `ACCT_TREND`, `ACCT_MOMENTUM`, `SLEEVE_TREND`, `SNAPSHOT_T1`) are the shared vocabulary for referencing seeded entities. Always import and use these constants rather than hard-coding string literals.

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
    reporting.py, sleeve_data.py
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
  sleeves.py               # insert_test_sleeve(), build_sleeve_env()
```

Helpers that are exclusively used by a single suite live co-located with that suite rather than in `tests/support/`:

- `tests/src/trading/interfaces/runtime/jobs/loaders.py` — runtime job module loaders and `run_module_as_main` (see [Interfaces Layer: `__main__` Entrypoint Tests](#interfaces-layer-__main__-entrypoint-tests))
- `tests/src/trading/services/auto_trading/factories.py` — auto-trading fakes and builders
- `tests/src/trading/services/admin/seed.py` — admin dataset seeding

**Convention:** if a co-located `factories.py` is imported from outside its own directory, move it to `tests/support/` under a domain-based name.
