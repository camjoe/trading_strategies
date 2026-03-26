# Tests

Repository test suite for trading, trends, backtesting, UI backend, and supporting scripts.

## Targeted Run

```powershell
python -m pytest -o addopts= tests/test_docs_freshness_check.py
```

Use `-o addopts=` when local environments do not have coverage plugins required by default pytest options.
