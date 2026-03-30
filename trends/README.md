# Trends Module

Stock trends analysis with `yfinance`, `matplotlib`, and technical indicators.

## Purpose

Provide a repeatable workflow for chart-based trend analysis and indicator generation across single tickers and categorized watchlists.

## Quick Start

1. Add your tickers in `trends/assets/run_tickers.txt` (one per line or comma-separated).
2. Run from the project root:

```sh
python trends/stock_trends.py
```

3. Charts are saved to `local/charts/`.

Optional:

```sh
python trends/stock_trends.py --explain
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
python trends/stock_trends.py

# Single ticker
python trends/stock_trends.py AAPL --period 1y --interval 1d

# From file or category
python trends/stock_trends.py --tickers-file trends/assets/run_tickers.txt
python trends/stock_trends.py --category tech --period 1y
python trends/stock_trends.py --list-categories
```

## Notes

- If `trends/assets/run_tickers.txt` exists, it is used by default.
- Multiple tickers run in batch mode (saved charts, no popup).
- Single ticker opens a chart window and also saves output.
- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.
- `--debug-columns` prints dataframe column shape before and after normalization.
