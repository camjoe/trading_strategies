# Trends Module

Stock trends analysis with `yfinance`, `matplotlib`, and technical indicators.

## Purpose

Provide a repeatable workflow for chart-based trend analysis and indicator generation across single tickers and categorized watchlists.

## Quick Start

1. Add your tickers in `trends/assets/run_tickers.txt` (one per line or comma-separated).
2. Run from the project root:

```sh
py -m trends
```

3. Charts are saved to `local/charts/`.

Optional:

```sh
py -m trends --explain
```

The script calculates moving averages, RSI/RS, MACD, and daily returns, then saves charts.

## Input Files

- `trends/assets/run_tickers.txt`: quick ticker list for normal runs.
- `trends/assets/ticker_categories.txt`: grouped ticker lists using `[category]` sections.

### `trends/assets/run_tickers.txt` format

```txt
# One per line or comma-separated
AAPL
MSFT, NVDA
SPY
```

### `trends/assets/ticker_categories.txt` format

```txt
[tech]
AAPL, MSFT, NVDA, AMZN

[etf]
SPY, QQQ, IWM
```

## Common Commands

All flags accept `--help` for the full reference.

```sh
# Run default ticker file
py -m trends

# Single ticker
py -m trends AAPL --period 1y --interval 1d

# From file or category
py -m trends --tickers-file trends/assets/run_tickers.txt
py -m trends --category tech --period 1y
py -m trends --list-categories
```

## Notes

- If `trends/assets/run_tickers.txt` exists, it is used by default.
- Multiple tickers run in batch mode (saved charts, no popup).
- Single ticker opens a chart window and also saves output.
- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.
- `--debug-columns` prints dataframe column shape before and after normalization.
