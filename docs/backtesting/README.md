# Backtesting

Backtesting is implemented in:
- `trading/backtesting/backtest.py`
- `trading/backtesting/backtest_data.py`
- `trading/backtesting/strategy_signals.py`

The module reuses account metadata from paper trading while storing run, trade, and equity history in dedicated backtest tables.

## Commands

Run single backtest:

```powershell
python trading/paper_trading.py backtest --account trend_v1 --lookback-months 12
```

Run backtest report:

```powershell
python trading/paper_trading.py backtest-report --run-id 1
```

Run monthly walk-forward backtest:

```powershell
python trading/paper_trading.py backtest-walk-forward --account trend_v1 --start 2025-01-01 --end 2025-12-31 --test-months 1 --step-months 1
```

Use monthly universe snapshots (`YYYY-MM.txt`) for reconstitution:

```powershell
python trading/paper_trading.py backtest --account trend_v1 --lookback-months 12 --universe-history-dir docs/backtesting/universe_history
```

## Safeguards and Approximation Notes

- Signals use prior-day data and execute on the next bar to reduce look-ahead bias.
- Daily adjusted close data is used; intraday path is not modeled.
- Stop-loss and take-profit behavior is approximate when evaluated on daily bars.
- LEAPs mode is approximate and requires explicit opt-in (`--allow-approximate-leaps`).
- Survivorship bias can occur if ticker universes are based only on present-day symbols.

## Related Docs

- `docs/Paper Trading.md`
- `docs/Strategies.md`
- `docs/backtesting/Tooling.md`
