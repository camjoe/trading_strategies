# Software Reference

Canonical software package inventory for the Software section of the documentation page.

## Projects in This Repository

| Project | Description |
| --- | --- |
| trading/ | Core trading engine for paper trading accounts, trade recording, position management, accounting, automation, reporting, and backtesting. |
| trends/ | Trend analysis module for fetching market data, computing technical indicators, and producing trend signals. |
| paper_trading_ui/ | Web interface for paper trading and backtesting with a FastAPI backend and TypeScript + Vite frontend. |
| common/ | Shared cross-project utilities including market data providers, ticker loading, repo paths, and time helpers. |

## Languages and Frameworks

| Language / Framework | Usage |
| --- | --- |
| Python | Core language for all trading logic, backtesting, data analysis, and the API backend. |
| TypeScript | Frontend UI (paper_trading_ui/frontend/) — provides type-safe client-side code. |
| SQL (SQLite) | Persistent storage for accounts, trades, equity snapshots, and backtest results. |
| FastAPI | REST API framework for the paper_trading_ui backend. |
| Vite | Frontend build tool and dev server for the TypeScript UI. |

## Data & Market Access

| Package | Version | Scope | Purpose |
| --- | --- | --- | --- |
| yfinance | ==1.2.0 | runtime | Primary market data source for daily OHLCV, adjusted close, and related Yahoo Finance history. |

## Analysis & Modeling

| Package | Version | Scope | Purpose |
| --- | --- | --- | --- |
| numpy | ==2.4.3 | runtime | Numerical array and vectorized math foundation for analytics and signal calculations. |
| pandas | ==3.0.1 | runtime | Core tabular and time-series data handling across trading, trends, and reporting flows. |

## Visualization

| Package | Version | Scope | Purpose |
| --- | --- | --- | --- |
| matplotlib | ==3.10.8 | runtime | Static chart rendering for trend analysis and exploratory visuals. |

## Backend & Validation

| Package | Version | Scope | Purpose |
| --- | --- | --- | --- |
| fastapi | ==0.120.4 | runtime | REST API framework for the paper_trading_ui backend. |
| pydantic | ==2.12.5 | runtime | Validation and schema modeling for backend requests, responses, and settings. |
| python-dotenv | ==1.2.1 | runtime | Loads environment variables for local backend and script configuration. |
| uvicorn[standard] | ==0.35.0 | runtime | ASGI server used to run the FastAPI application locally and in lightweight deployments. |

## Developer Tooling

| Package | Version | Scope | Purpose |
| --- | --- | --- | --- |
| httpx | >=0.23.0,<1.0.0 | development | HTTP client used in API and integration tests. |
| hypothesis | ==6.131.26 | development | Property-based testing library for broader edge-case coverage. |
| pytest | ==8.3.5 | development | Primary test runner for unit and integration suites. |
| pytest-cov | ==6.0.0 | development | Coverage plugin layered onto pytest for repository quality gates. |
| pytest-mock | ==3.14.0 | development | pytest integration for mocking and patch-based test setup. |
