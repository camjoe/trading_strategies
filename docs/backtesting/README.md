# Backtesting

Backtesting is implemented in:
- `trading/features/backtesting/backtest.py`
- `trading/features/backtesting/backtest_data.py`
- `trading/features/backtesting/strategy_signals.py`

Compatibility import shims are also available at:
- `trading/backtesting/backtest.py`
- `trading/backtesting/backtest_data.py`
- `trading/backtesting/strategy_signals.py`

The module reuses account metadata from paper trading while storing run, trade, and equity history in dedicated backtest tables.

## Commands

Run single backtest:

```powershell
python -m trading.paper_trading backtest --account trend_v1 --lookback-months 12
```

Run backtest report:

```powershell
python -m trading.paper_trading backtest-report --run-id 1
```

Rank historical runs by total return:

```powershell
python -m trading.paper_trading backtest-leaderboard --limit 10
python -m trading.paper_trading backtest-leaderboard --strategy mean
```

Run multi-account batch comparison:

```powershell
python -m trading.paper_trading backtest-batch --accounts trend_v1,meanrev_v1 --lookback-months 12 --run-name-prefix phase1
```

Run monthly walk-forward backtest:

```powershell
python -m trading.paper_trading backtest-walk-forward --account trend_v1 --start 2025-01-01 --end 2025-12-31 --test-months 1 --step-months 1
```

Use monthly universe snapshots (`YYYY-MM.txt`) for reconstitution:

```powershell
python -m trading.paper_trading backtest --account trend_v1 --lookback-months 12 --universe-history-dir docs/backtesting/universe_history
```

## Strategy Notes

- Phase 2 strategy ids are documented in `docs/Strategies.md`.
- Backtests resolve active strategy through shared rotation-aware logic.
- If account rotation metadata is configured, backtests use the resolved active strategy.

## Safeguards and Approximation Notes

- Signals use prior-day data and execute on the next bar to reduce look-ahead bias.
- Daily adjusted close data is used; intraday path is not modeled.
- Stop-loss and take-profit behavior is approximate when evaluated on daily bars.
- LEAPs mode is approximate and requires explicit opt-in (`--allow-approximate-leaps`).
- Survivorship bias can occur if ticker universes are based only on present-day symbols.

## Tooling Notes

Backtesting in this repository runs on the in-house engine under:

- `trading/backtesting/`

Optional external packages that may be evaluated later are tracked in:

- `docs/Tooling and Packages.md`

Operational notes:

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines and benchmark returns.

## Related Docs

- `trading/README.md`
- `docs/Strategies.md`
