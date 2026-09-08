# Trends Module

Stock trends analysis with `yfinance`, `matplotlib`, and technical indicators.

## Purpose

Provide a repeatable workflow for chart-based trend analysis and indicator generation across single tickers and categorized watchlists.

## Quick Start

1. Add your tickers in `apps/trends/assets/run_tickers.txt` (one per line or comma-separated).
2. Run from the project root:

```sh
python -m trends
```

3. Charts are saved to `local/charts/`.

Optional:

```sh
python -m trends --explain
```

The script calculates moving averages, RSI/RS, MACD, and daily returns, then saves charts.

## Input Files

- `apps/trends/assets/run_tickers.txt`: quick ticker list for normal runs.
- `apps/trends/assets/ticker_categories.txt`: grouped ticker lists using `[category]` sections.

### `apps/trends/assets/run_tickers.txt` format

```txt
# One per line or comma-separated
AAPL
MSFT, NVDA
SPY
```

### `apps/trends/assets/ticker_categories.txt` format

```txt
[tech]
AAPL, MSFT, NVDA, AMZN

[etf]
SPY, QQQ, IWM
```

## Commands

All flags accept `--help` for the full reference. Commands assume the repository virtual environment
created in the root README is active.

```sh
# Run default ticker file
python -m trends

# Single ticker
python -m trends AAPL --period 1y --interval 1d

# From file or category
python -m trends --tickers-file apps/trends/assets/run_tickers.txt
python -m trends --category tech --period 1y
python -m trends --list-categories
```

## Notes

- If `apps/trends/assets/run_tickers.txt` exists, it is used by default.
- Multiple tickers run in batch mode (saved charts, no popup).
- Single ticker opens a chart window and also saves output.
- Category names are case-insensitive.
- Lines starting with `#` in ticker files are ignored.
- Tickers can be written one per line or comma-separated.

## Known Duplication

`calculate_rs_rsi` and `calculate_macd` exist **twice** — here in
`apps/trends/indicators.py` and in src/trading/domain. The two copies are
functionally identical, down to the same edge-case handling (coercing `inf`/`-inf` to `NaN`, and
treating a flat rolling window as neutral momentum with `RS = 1.0`). They differ only in variable
names and comment style, which means the same subtle fixes were made in both places.

`calculate_bollinger_bands`, `calculate_annualized_volatility_pct`, `add_trend_features`, and
`print_indicator_explanations` are trends-only and are not duplicated.

**Fix direction:** this module should import the two shared functions from
`trading.domain.indicators` and drop its own copies. That is already legal — this app imports from
the main tree today (`infrastructure.market_data.factory`, `trading.services.market_data`,
`common.*`), so the boundary is already porous and no new dependency edge is created.

Worth resolving **before** this app is built out, so a larger surface is not grown on top of a
divergence risk.

## If This Gets Built Out

Open product question, and it changes what "building this out" means:

- **A ticker-exploration surface** — look at a symbol, read its indicators, decide whether it is
  worth investigating. Sits alongside strategy evaluation without overlapping it. If it becomes a
  web tab it is a **Research** surface (see the tab grouping in
  [the web app README](../paper_trading_web/README.md)).
- **A charting layer the main app absorbs** — in which case this is not renamed but dissolved, and
  its plotting code becomes shared chart primitives for the web app.

Decide which before investing; a rename only makes sense under the first reading.

### Charting guidance

Today this app renders with `matplotlib` to PNG files under `local/charts/`. That is fine for a CLI
workflow, but **it does not transfer to the web app**, which renders charts as inline SVG.

If charts move to the web surface, two constraints apply:

- **The frontend has zero runtime dependencies** (`dependencies: {}` — only TypeScript and Vite in
  dev). Adding a charting library would be the first one. For the chart types involved — line and
  equity curves, scatter, distribution bars — hand-rolled SVG is sufficient and is already done once
  in `components/account-detail/sections-snapshots.ts`.
- **Charts should theme off `styles/tokens.css`** so they match the application rather than looking
  like an embedded widget with its own palette. Inline SVG inherits this for free; a canvas-based
  library does not.

Load the **`dataviz` skill** before building any chart work. It covers making a set of
visualizations read as one system — colour formula and accessibility, chart-type selection, axis and
legend rules, and stat-tile/dashboard layout — which is the difference between "has charts" and
"looks considered."

## Related Docs

- [Web App README](../paper_trading_web/README.md) — tab grouping, frontend boundary notes
- [Backtesting](../../docs/reference/backtesting.md) — the backtest / optimization / walk-forward
  capability split, for how this app's analysis relates to strategy evaluation
- [Architecture Conventions](../../docs/architecture/architecture-conventions.md) — layering and
  import-direction rules that govern what this app may import
