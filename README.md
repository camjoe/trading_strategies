# Trading Trends Starter

Simple Python workflow for charting stock trends with `yfinance` and `matplotlib`.

## Quick Start

1. Add your tickers in `run_tickers.txt` (one per line or comma-separated).
2. Run the script from the project root:

```powershell
python trends/stock_trends.py
```

3. Check output charts in `charts/`.

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

It saves chart images into `charts/` each run.

## Input Files

- `run_tickers.txt`: quick ticker list for normal runs.
- `ticker_categories.txt`: grouped ticker lists using `[category]` sections.

### `run_tickers.txt` format

```txt
# One per line or comma-separated
AAPL
MSFT, NVDA
SPY
```

### `ticker_categories.txt` format

```txt
[tech]
AAPL, MSFT, NVDA, AMZN

[etf]
SPY, QQQ, IWM
```

## Basic Usage

From the project root:

```powershell
python trends/stock_trends.py
```

Behavior:
- If `run_tickers.txt` exists, those tickers are used by default.
- If multiple tickers are selected, charts are saved in batch mode (no popup windows).
- If one ticker is selected, chart window opens and chart is also saved.

## Common Examples

Run one ticker directly:

```powershell
python trends/stock_trends.py AAPL --period 1y --interval 1d
```

Run using `run_tickers.txt`:

```powershell
python trends/stock_trends.py --tickers-file run_tickers.txt --period 6mo --interval 1d
```

Run a category from `ticker_categories.txt`:

```powershell
python trends/stock_trends.py --category tech --period 1y --interval 1d
```

List available categories:

```powershell
python trends/stock_trends.py --list-categories
```

Show indicator explanations while running:

```powershell
python trends/stock_trends.py --category etf --explain
```

Use a custom category file path:

```powershell
python trends/stock_trends.py --category banks --category-file ticker_categories.txt
```

Debug column structure (useful when data-provider schema changes):

```powershell
python trends/stock_trends.py NVDA --debug-columns
```

## Notes

- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.
- `--debug-columns` prints dataframe column shape before and after normalization.

## Backtesting

Backtesting and walk-forward simulation documentation is now in:
- `docs/backtesting/README.md`

## Documentation Index

For a full map of project docs, see:
- `docs/README.md`

## Testing

Run the full test suite from project root:

```powershell
python -m pytest
```

Coverage is configured in `pytest.ini` and includes:
- Terminal report with missing lines
- `coverage.xml` output (used by CI artifact upload)
- Coverage collection for both `trading` and `trends` packages
- Minimum coverage threshold of 35% (baseline, can be raised over time)
