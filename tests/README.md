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
