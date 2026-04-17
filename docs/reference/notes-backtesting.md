# Backtesting

Backtesting is implemented in:
- `trading/backtesting/backtest.py`
- `trading/backtesting/repositories/`
- `trading/backtesting/services/`
- `trading/backtesting/domain/`

The module reuses account metadata from paper trading while storing run, trade, and equity history in dedicated backtest tables.

## Layering and Ownership

Backtesting follows a layered structure:

- Repositories (`trading/backtesting/repositories/`): SQL reads/writes only.
- Services (`trading/backtesting/services/`): orchestration, model mapping, and workflow logic.
- Domain (`trading/backtesting/domain/`): pure calculations and policy helpers.
- Entrypoint (`trading/backtesting/backtest.py`): public API composition and call routing.

Detailed rationale is in:

- `docs/reference/adr-backtesting-layering.md`

## Commands

All backtesting commands are under `python -m trading.interfaces.cli.main` and accept `--help` for the full reference.

```sh
# Single backtest
python -m trading.interfaces.cli.main backtest --account trend_v1 --lookback-months 12

# Walk-forward
python -m trading.interfaces.cli.main backtest-walk-forward --account trend_v1 --start 2025-01-01 --end 2025-12-31 --test-months 1 --step-months 1

# Persisted walk-forward detail report
python -m trading.interfaces.cli.main backtest-walk-forward-report --account trend_v1

# Batch comparison
python -m trading.interfaces.cli.main backtest-batch --accounts trend_v1,meanrev_v1 --lookback-months 12

# Leaderboard
python -m trading.interfaces.cli.main backtest-leaderboard --limit 10
```

## Scheduled Refresh

Recurring refreshes for persisted account backtests are handled by:

- `python -m trading.interfaces.runtime.jobs.daily_backtest_refresh`

Key behavior:

- explicit opt-in via `--enable-run` or `DAILY_BACKTEST_REFRESH_ENABLED=1`
- duplicate same-day run guard unless `--force-run` is supplied
- transient retry handling for market-data failures
- machine-readable JSON artifacts under `local/exports/daily_backtest_refresh/`

## Strategy Notes

- Phase 2 strategy ids are documented in `docs/reference/notes-strategies.md`.
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

Dependency definitions live in:

- `requirements-base.txt`
- `requirements-dev.txt`

Operational notes:

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines and benchmark returns.

## Related Docs

- `docs/reference/notes-strategies.md`
- `docs/reference/adr-backtesting-layering.md`
