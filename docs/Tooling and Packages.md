# Tooling and Packages

Reference list of useful Python packages, data providers, and VS Code extensions for trading research workflows.

## Requirement Files by Purpose

- `requirements/base.txt`: core runtime for `trading/`, `trends/`, and the UI backend.
- `requirements/dev.txt`: runtime plus test dependencies.
- `requirements/research.txt`: optional notebook and modeling extras.
- `requirements.txt`: compatibility alias to `requirements/dev.txt`.

## Currently Used in This Repo

### Runtime and API

- `yfinance` (market data)
- `fastapi` and `uvicorn` (UI backend)
- `python-dotenv` (backend config)
- `sqlite3` from the Python standard library (database access)

### Analysis and Trading Workflows

- `pandas`
- `numpy`
- `statsmodels`
- `matplotlib`

### Testing and Quality

- `pytest`
- `pytest-cov`

### Frontend and Tooling

- Vite and TypeScript (under `paper_trading_ui/frontend`)