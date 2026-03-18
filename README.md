# Trading Strategies

A Python suite for stock trends analysis, backtesting, paper trading, and strategy development.

## Project Overview

This repository contains tools for:

- **Trends Analysis**: Chart technical indicators and moving averages for stock tickers using `yfinance` and `matplotlib`.
- **Backtesting**: Walk-forward simulation of trading strategies on historical data.
- **Paper Trading**: Live strategy execution with simulated portfolio management.
- **UI Dashboard**: Real-time monitoring of paper trading activity via a web interface.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `trends/` | Stock trends analysis and indicator calculations. |
| `trading/` | Core trading logic: accounts, pricing, orders, reporting, backtesting. |
| `paper_trading_ui/` | Web dashboard (FastAPI backend + TypeScript frontend) for paper trading. |
| `docs/` | Detailed documentation and guides. |
| `tests/` | Test suite for all modules. |

## Python Setup

Choose the dependency set that matches your purpose:

```powershell
# Core runtime for trends, trading, and UI backend
pip install -r requirements/base.txt

# Runtime plus test dependencies
pip install -r requirements/dev.txt

# Optional notebook / modeling extras (research and experimentation)
pip install -r requirements/research.txt
```

**Compatibility Note:**
- `requirements.txt` points to `requirements/dev.txt` for backward compatibility.
- `paper_trading_ui/backend/requirements.txt` points to `requirements/base.txt`.

## Quick Start

### Trends Analysis

See [trends/README.md](trends/README.md) for full documentation and usage examples.

### Backtesting

See [docs/backtesting/README.md](docs/backtesting/README.md) for walk-forward simulation and strategy testing.

### Paper Trading

See [trading/README.md](trading/README.md) for paper trading commands, account profiles, and scheduler operations.

Direct links:

- [Main commands](trading/README.md#main-commands)
- [Apply account profiles](trading/README.md#apply-account-profiles)
- [Auto-trading](trading/README.md#auto-trading)
- [Daily scheduler (Windows)](trading/README.md#daily-scheduler-windows)

## Testing

Run the full test suite from the project root:

```powershell
python -m pytest
```

Tests cover both `trading` and `trends` packages with a baseline of 35% coverage.

## Documentation Index

For detailed documentation on all components, see [docs/README.md](docs/README.md).
