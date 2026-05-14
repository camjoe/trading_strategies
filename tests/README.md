# Tests

Repository test suite for trading, trends, backtesting, UI backend, and supporting scripts.

## Purpose

Provide reliable verification coverage for runtime behavior, data operations, UI backend flows, and supporting repository scripts.

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
