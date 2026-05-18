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
python -m scripts.checks.run_suite trading/services

# A single service
python -m scripts.checks.run_suite trading/services/market_data
python -m scripts.checks.run_suite trading/services/promotion

# Multiple suites combined
python -m scripts.checks.run_suite trading/services/market_data trading/services/promotion

# Other top-level areas
python -m scripts.checks.run_suite trading/backtesting
python -m scripts.checks.run_suite trading/repositories
python -m scripts.checks.run_suite trading/interfaces
python -m scripts.checks.run_suite paper_trading_ui
python -m scripts.checks.run_suite common
```

### Target an individual file

```sh
python -m scripts.checks.run_suite trading/services/market_data/test_features.py
```

### Pass extra flags to pytest

```sh
# Verbose, no coverage (fast iteration)
python -m scripts.checks.run_suite trading/services -v --no-cov

# Run only tests matching a keyword
python -m scripts.checks.run_suite trading/services/market_data -k "test_provider"
```

### Available service suites

| Suite name | Tests directory |
|---|---|
| `trading/services` | `tests/trading/services/` |
| `trading/services/accounting` | `tests/trading/services/accounting/` |
| `trading/services/accounts` | `tests/trading/services/accounts/` |
| `trading/services/admin` | `tests/trading/services/admin/` |
| `trading/services/analysis` | `tests/trading/services/analysis/` |
| `trading/services/auto_trading` | `tests/trading/services/auto_trading/` |
| `trading/services/evaluation` | `tests/trading/services/evaluation/` |
| `trading/services/ibkr_paper_monitor` | `tests/trading/services/ibkr_paper_monitor/` |
| `trading/services/market_data` | `tests/trading/services/market_data/` |
| `trading/services/pricing` | `tests/trading/services/pricing/` |
| `trading/services/profiles` | `tests/trading/services/profiles/` |
| `trading/services/promotion` | `tests/trading/services/promotion/` |
| `trading/services/reporting` | `tests/trading/services/reporting/` |
| `trading/services/sleeves` | `tests/trading/services/sleeves/` |

Two source service modules (`profile_source`, `universe_resolver`) are covered by flat test files at `tests/trading/services/` rather than subdirectories; target them via the `trading/services` suite or directly by file path.  `runtime_settings` and `runtime_throttle` do not yet have dedicated test subdirectories; use `trading/services` to include any tests that exist at the parent level.

### Targeted runs in GitHub Actions

Use the **Targeted Tests** workflow (`targeted-tests.yml`) for focused validation on a branch without waiting for the full CI suite:

```sh
gh workflow run targeted-tests.yml --ref <your-branch> -f suites="trading/services/market_data"
gh workflow run targeted-tests.yml --ref <your-branch> -f suites="trading/services/market_data,trading/services/promotion"
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

- `tests/trading/interfaces/runtime/jobs/test_daily_snapshot_helpers.py`
- `tests/trading/interfaces/runtime/jobs/test_daily_snapshot_main.py`

Run only this test slice:

```sh
python -m pytest --no-cov \
  tests/trading/interfaces/runtime/jobs/test_daily_snapshot_helpers.py \
  tests/trading/interfaces/runtime/jobs/test_daily_snapshot_main.py
```

## Fixture Hierarchy

- `tests/conftest.py`: cross-suite fixtures, including `conn` (writable) and `seeded_conn` (read-only seeded DB).
- Directory-level `conftest.py` files provide subtree-scoped fixtures (e.g. `sleeve_env`, `account_id`).
- `tests/trading/services/market_data/conftest.py`: market-data service fixtures, including provider reset per test.
- `tests/paper_trading_ui/conftest.py`: UI backend fixtures, including `api_client` with isolated DB backend.

## Database Fixtures — Which One to Use

**Use `conn`** when the test needs to write data (inserts, updates, deletes). It is function-scoped: each test gets a fresh, empty SQLite DB.

**Use `seeded_conn`** when the test only reads. It is session-scoped and opens the pre-seeded DB read-only (`?mode=ro`). This is faster and does not risk corrupting shared state. The seed covers accounts, trades, snapshots, a sleeve, strategy assignments, daily metrics, backtest runs, and promotion reviews.

Named constants from `tests/support/seed_db.py` (e.g. `ACCT_TREND`, `ACCT_MOMENTUM`, `SLEEVE_TREND`, `SNAPSHOT_T1`) are the shared vocabulary for referencing seeded entities. Always import and use these constants rather than hard-coding string literals.

## State Isolation

- Database backend is switched to a `tmp_path` SQLite file inside fixtures and restored in a `finally` block.
- `seeded_conn` is enforced read-only at the OS/VFS layer via `?mode=ro` URI flag — not just `PRAGMA query_only`.
- Market data provider environment variables are reset before and after each `tests/trading/services/market_data` test.
- Tests that mutate global state should always restore it in fixture teardown.

## Audit Notes

- Full repository validation remains `python -m pytest` from repo root.
- Cross-stack smoke validation is `python -m scripts.run_checks --profile ci`.
- For parser/default-path changes, include focused checks for CLI parser/handler coverage under `tests/trading/interfaces/cli/` and runtime-job coverage under `tests/trading/interfaces/runtime/jobs/`.
