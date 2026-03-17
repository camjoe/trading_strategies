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

## Optional / Future Evaluation

### Data Source Alternatives

- `yahooquery`
- `pandas-datareader`
- `alpha_vantage`
- `tiingo`
- `polygon-api-client`
- `ccxt` (crypto exchange data)

### Indicators and Technical Analysis

- `scikit-learn`
- `scipy`
- `pandas-ta`
- `ta`

### Visualization and Reporting

- `plotly`
- `mplfinance`

### Backtesting and Performance

Backtesting-specific tools and notes have been moved to:
- `docs/backtesting/Tooling.md`

Additional candidates:
- `quantstats`
- `vectorbt`
- `backtrader`

### Additional Data and API Access

- `requests`
- `httpx`

### Deep Learning Candidates

- `torch`
- `pytorch-lightning`

## VS Code Extensions

- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-toolsai.jupyter`
- `charliermarsh.ruff`
- `ms-python.black-formatter`
- `eamodio.gitlens`

## Notes

- Keep production-sensitive workflows on more reliable paid feeds when needed.
- Free data is useful for prototyping but can have gaps, revisions, or rate limits.
- Pin versions in `requirements/base.txt`, `requirements/dev.txt`, and `requirements/research.txt` for reproducibility.
