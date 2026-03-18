# Trends Module

Stock trends analysis with `yfinance`, `matplotlib`, and technical indicators.

## Quick Start

1. Add your tickers in `trends/assets/run_tickers.txt` (one per line or comma-separated).
2. Run from the project root:

```powershell
python trends/stock_trends.py
```

3. Charts are saved to `local/charts/`.

Optional:

```powershell
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

Run one ticker:

```powershell
python trends/stock_trends.py AAPL --period 1y --interval 1d
```

Run from file:

```powershell
python trends/stock_trends.py --tickers-file trends/assets/run_tickers.txt --period 6mo --interval 1d
```

Run category:

```powershell
python trends/stock_trends.py --category tech --period 1y --interval 1d
```

List categories:

```powershell
python trends/stock_trends.py --list-categories
```

Show explanations:

```powershell
python trends/stock_trends.py --category etf --explain
```

Custom category file:

```powershell
python trends/stock_trends.py --category banks --category-file trends/assets/ticker_categories.txt
```

Debug data columns:

```powershell
python trends/stock_trends.py NVDA --debug-columns
```

## Notes

- If `trends/assets/run_tickers.txt` exists, it is used by default.
- Multiple tickers run in batch mode (saved charts, no popup).
- Single ticker opens a chart window and also saves output.
- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.
- `--debug-columns` prints dataframe column shape before and after normalization.
