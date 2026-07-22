# Trading Strategies

A system for developing, evaluating, and progressively automating quantitative trading strategies. It
takes a strategy from **backtest → walk-forward → paper → human-gated live**, continuously compares
strategies against one another, and rotates toward the best performer — with the goal of a
data-driven automated trader deployable from paper to a live IBKR account in a near-identical way.

> [!WARNING]
> This repository is educational and research software. It is not financial, investment, tax, or
> legal advice, and it is not represented as production-ready investment infrastructure. Trading
> involves risk of substantial loss. Backtests, simulations, and paper-trading results do not predict
> future performance. You are responsible for reviewing the software, protecting broker credentials,
> and deciding whether any use—including connection to a broker—is appropriate.

## Availability and licensing

This source repository is publicly viewable on GitHub and is being prepared for a future open-source
release, but it is not currently offered under an open-source license. Until a `LICENSE` file is
added, no permission to use, modify, or redistribute the source is granted beyond rights provided by
applicable law and GitHub's Terms of Service. The planned license is the Apache License 2.0; this
statement records intent only and does not grant that license.

See [Open-Source Readiness](docs/reference/open-source-readiness.md) for the staged preparation plan,
including the deferred license decision and future separation of private strategy implementations.

**Start here:** [`docs/overview.md`](docs/overview.md) — the definitive explainer of what the app is,
what it can do today (with honest gaps), how it works, and where it's going.

## Project Overview

This repository provides tools for:

- **Trends Analysis**: Chart technical indicators and moving averages for stock tickers using `yfinance` and `matplotlib`.
- **Backtesting**: Historical and walk-forward simulation with persisted run and per-window reporting.
- **Paper Trading**: Live strategy execution with simulated portfolio management, benchmark tracking, and promotion review workflows.
- **UI Dashboard**: Real-time monitoring of paper trading activity via a web interface, including live benchmark overlays.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `apps/trends/` | Stock trends analysis and indicator calculations. |
| `src/trading/` | Core trading logic: accounts, pricing, orders, reporting, backtesting. |
| `src/infrastructure/` | Concrete adapters isolated from the domain: brokers, market-data, feature providers, database. |
| `src/common/` | Shared kernel utilities used across packages (coercion, constants, paths, tickers, time). |
| `apps/paper_trading_web/` | Web dashboard (FastAPI backend + TypeScript frontend) for paper trading. |
| `.ai/skills/` | Reusable skill definitions and templates for localized overlays. |
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
- Run trading scripts as Python modules from the repository root using the active venv interpreter:
  ```sh
  .venv\Scripts\python -m trading.interfaces.cli.main init   # Windows
  .venv/bin/python -m trading.interfaces.cli.main init        # macOS/Linux
  ```

## CI Smoke Check

Run the same core checks used by GitHub Actions from the repository root:

```sh
python -m scripts.run_checks ci
```

For deterministic local cleanup before re-running checks:

```sh
python -m scripts.fix_checks
```

This runs Ruff safe fixes, Ruff formatting, generated API/software reference-doc asset sync, and docs drift fixes (DB schema Quick Reference sync, stale map row removal).

## Quick Start

### Trends Analysis

See [apps/trends/README.md](apps/trends/README.md) for full documentation and usage examples.

### Backtesting

See [docs/reference/backtesting.md](docs/reference/backtesting.md) for backtest, walk-forward, and scheduled refresh documentation.

### Paper Trading

See [src/trading/README.md](src/trading/README.md) for paper trading commands, account profiles, and scheduler operations.

### UI Dashboard

Run the backend and frontend together with the launch script:

```sh
python -m scripts.launch_ui
```

Or start each service separately (required when using the Python debugger — see below):

```sh
# Terminal 1 — FastAPI backend (no --reload so pdb stdin works)
python -m uvicorn paper_trading_web.backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Vite frontend dev server
cd apps/paper_trading_web/frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

#### Debugging with pdb

Insert a `breakpoint()` call anywhere in backend Python code, then start the services separately (as above, **without** `--reload` so pdb can read from stdin).

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
