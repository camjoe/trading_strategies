# Trading Strategies

A Python suite for stock trends analysis, backtesting, paper trading, and strategy development.

## Project Overview

This repository contains tools for:

- **Trends Analysis**: Chart technical indicators and moving averages for stock tickers using `yfinance` and `matplotlib`.
- **Backtesting**: Historical and walk-forward simulation with persisted run and per-window reporting.
- **Paper Trading**: Live strategy execution with simulated portfolio management, benchmark tracking, and promotion review workflows.
- **UI Dashboard**: Real-time monitoring of paper trading activity via a web interface, including live benchmark overlays.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `trends/` | Stock trends analysis and indicator calculations. |
| `trading/` | Core trading logic: accounts, pricing, orders, broker integration (paper + Interactive Brokers), reporting, backtesting. |
| `paper_trading_ui/` | Web dashboard (FastAPI backend + TypeScript frontend) for paper trading. |
| `docs/` | Detailed documentation and guides. |
| `tests/` | Test suite for all modules. |

## Python Setup

Choose the dependency set that matches your purpose:

```sh
# Core runtime for trends, trading, and UI backend
pip install -r requirements-base.txt

# Runtime plus test dependencies
pip install -r requirements-dev.txt
```

**Execution Note:**
- All trading scripts must be run as Python modules from the repository root, e.g.,
  ```sh
  python -m trading.interfaces.cli.main init
  ```

## CI Smoke Check

Run the same core checks used by GitHub Actions from the repository root:

```sh
python -m scripts.run_checks --profile ci
```

Optional flags:

```sh
# Skip frontend checks
python -m scripts.run_checks --profile ci --skip-frontend

# Skip python checks
python -m scripts.run_checks --profile ci --skip-python

# Explicitly install ruff/mypy before quality gates
python -m scripts.run_checks --profile ci --install-python-tools
```

Single-source validation guidance lives in:

- `scripts/README.md` for script behavior and flags.
- `.github/DOCS_PRECOMMIT_POLICY.md` for docs-impact audit workflow and bot request templates.

## Quick Start

### Trends Analysis

See [trends/README.md](trends/README.md) for full documentation and usage examples.

### Backtesting

See [docs/reference/notes-backtesting.md](docs/reference/notes-backtesting.md) for backtest, walk-forward, and scheduled refresh documentation.

### Paper Trading

See [trading/README.md](trading/README.md) for paper trading commands, account profiles, and scheduler operations.

### UI Dashboard

Run the backend and frontend together with the launch script:

```sh
python scripts/launch_ui.py
```

Or start each service separately (required when using the Python debugger — see below):

```sh
# Terminal 1 — FastAPI backend (no --reload so pdb stdin works)
python -m uvicorn paper_trading_ui.backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Vite frontend dev server
cd paper_trading_ui/frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

#### Debugging with pdb

Insert a
`breakpoint()` call anywhere in the backend Python code, then start the services
separately (as above, **without** `--reload` so pdb can read from stdin).

When the breakpoint is hit the browser request will pause and a `(Pdb)` prompt
appears in the backend terminal.

## Testing

Run the full test suite from the project root:

```sh
python -m pytest
```

Tests cover both `trading` and `trends` packages with a minimum 70% coverage threshold.

## Documentation Index

For detailed documentation on all components, see [docs/README.md](docs/README.md).
