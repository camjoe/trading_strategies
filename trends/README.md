# Trends Module

Stock trends analysis with `yfinance`, `matplotlib`, and technical indicators.

## Quick Start

1. Add your tickers in `trends/assets/run_tickers.txt` (one per line or comma-separated).
2. Run from the project root:

```powershell
python trends/stock_trends.py
```

3. Charts are saved to `local/charts/`.

Optional first run with explanations:

```powershell
python trends/stock_trends.py --explain
```

## What This Script Does

`trends/stock_trends.py` downloads market data and calculates:
- Moving averages: `MA20`, `MA50`, `MA200`
- `RS` and `RSI14`
- `MACD`, `MACDSignal`, and `MACDHist`
- Daily return percentage

It saves chart images into `local/charts/` each run.

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

## Usage Examples

### Basic run

From the project root:

```powershell
python trends/stock_trends.py
```

Behavior:
- If `trends/assets/run_tickers.txt` exists, those tickers are used by default.
- If multiple tickers are selected, charts are saved in batch mode (no popup windows).
- If one ticker is selected, chart window opens and chart is also saved.

### Run one ticker directly

```powershell
python trends/stock_trends.py AAPL --period 1y --interval 1d
```

### Run using `trends/assets/run_tickers.txt`

```powershell
python trends/stock_trends.py --tickers-file trends/assets/run_tickers.txt --period 6mo --interval 1d
```

### Run a category from `ticker_categories.txt`

```powershell
python trends/stock_trends.py --category tech --period 1y --interval 1d
```

### List available categories

```powershell
python trends/stock_trends.py --list-categories
```

### Show indicator explanations while running

```powershell
python trends/stock_trends.py --category etf --explain
```

### Use a custom category file path

```powershell
python trends/stock_trends.py --category banks --category-file trends/assets/ticker_categories.txt
```

### Debug column structure

```powershell
python trends/stock_trends.py NVDA --debug-columns
```

(Useful when data-provider schema changes.)

## Notes

- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.
- `--debug-columns` prints dataframe column shape before and after normalization.
