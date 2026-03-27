# Tests

Repository test suite for trading, trends, backtesting, UI backend, and supporting scripts.

## Targeted Run

```powershell
python -m pytest -o addopts= tests/test_docs_freshness_check.py
```

Use `-o addopts=` when local environments do not have coverage plugins required by default pytest options.

## Daily Snapshot Tests

Daily snapshot scheduler coverage lives in:

- `tests/trading/test_daily_snapshot_script.py`

Run only this test module:

```powershell
python -m pytest --no-cov tests/trading/test_daily_snapshot_script.py
```

## Fixture Hierarchy

- `tests/conftest.py`: cross-suite fixtures, including isolated SQLite connection setup via `conn`.
- `tests/common/conftest.py`: common module fixtures, including market data provider reset per test.
- `tests/paper_trading_ui/conftest.py`: UI backend fixtures, including `api_client` with isolated DB backend.

## State Isolation

- Database backend is switched to a `tmp_path` SQLite file inside fixtures and restored in a `finally` block.
- Market data provider environment variables are reset before and after each `tests/common` test.
- Tests that mutate global state should always restore it in fixture teardown.
