# Backtesting

Type: notes
Status: Active
Created: 2026-03-14
Last Reviewed: 2026-07-09
Purpose: Reference for backtesting commands, layering overview, and safeguards.
Related: [ADR: Backtesting Layering](../adr/002-backtesting-layering.md), [Trading Package Map](../maps/trading-package-map.md)

Backtesting is implemented in:
- `src/trading/backtesting/backtest.py`
- `src/trading/backtesting/repositories/`
- `src/trading/backtesting/services/`
- `src/trading/backtesting/domain/`

The module reuses account metadata from paper trading while storing run, trade, and equity history in dedicated backtest tables.

## Layering and Ownership

Backtesting follows a layered structure:

- Repositories (`src/trading/backtesting/repositories/`): SQL reads/writes only.
- Services (`src/trading/backtesting/services/`): orchestration, model mapping, and workflow logic.
- Domain (`src/trading/backtesting/domain/`): pure calculations and policy helpers.
- Entrypoint (`src/trading/backtesting/backtest.py`): public API composition and call routing.

Detailed rationale is in:

- `docs/adr/002-backtesting-layering.md`

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

- `python -m trading.interfaces.runtime.jobs.daily.backtest_refresh`

Key behavior:

- explicit opt-in via `--enable-run` or `DAILY_BACKTEST_REFRESH_ENABLED=1`
- duplicate same-day run guard unless `--force-run` is supplied
- transient retry handling for market-data failures
- machine-readable JSON artifacts under `local/exports/daily_backtest_refresh/`

### Freshness cadence (advisory)

Every strategy evaluation carries an advisory **backtest freshness** diagnostic
(P12): the age of the newest backtest run (`backtest_runs.created_at`) measured
against the evaluation's generation time. When that age exceeds the stale
threshold (default **3 days**, `DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS` in
`trading.domain.backtest_freshness`) the diagnostic is flagged stale.

It is **advisory only** — it never blocks rotation or promotion and never
changes confidence or the blended score. It surfaces so operators can spot
evidence that has drifted (e.g. the refresh job is disabled or failing):

- CLI `report` / `compare-strategies`: a `backtest_age=<n>d (fresh|stale)`
  fragment on the evaluation summary line.
- CLI `promotion-status`: a `Backtest Freshness` line.
- Web: `backtestFreshness` on the evaluation detail payload and a `backtestStale`
  flag on the summary, shown in the promotion evidence grid and the compare view.

If stale evidence is later proven to skew decisions, this advisory is the hook
to tighten into confidence decay or a hard gate.

### Remediation

The freshness signal drives remediation — refreshing stale or missing backtests
across each account's rotation candidate strategies (incumbent + challenger
schedule), not just the active one:

- On demand: `python -m trading.interfaces.cli.main refresh-stale-backtests`
  (`--account` filter, `--dry-run` to list targets, `--limit` to cap a batch).
- Scheduled: the `Trading\DailyBacktestRefresh` job re-runs only the drifted
  backtests each day (see [runtime-jobs.md](runtime-jobs.md)).

Candidate strategy names are canonicalized through the strategy catalog, so an
aliased challenger (e.g. `macd_trend` → `macd`) matches its stored backtest and
is not re-run once fresh.

## Strategy Notes

- Phase 2 strategy ids are documented in `docs/reference/strategies.md`.
- Backtests resolve active strategy through shared rotation-aware logic.
- If account rotation metadata is configured, backtests use the resolved active strategy.
- Paper results before 2026-07-03 are not strategy evidence. Before the execution loop was closed,
  the paper trade path used a placeholder instead of strategy signals.

## Safeguards and Approximation Notes

- Signals use prior-day data and execute on the next bar to reduce look-ahead bias.
- Daily adjusted close data is used; intraday path is not modeled.
- Stop-loss and take-profit behavior is approximate when evaluated on daily bars.
- LEAPs mode is approximate and requires explicit opt-in (`--allow-approximate-leaps`).
- Survivorship bias can occur if ticker universes are based only on present-day symbols.

## Tooling Notes

Backtesting in this repository runs on the in-house engine under:

- `src/trading/backtesting/`

Dependency definitions live in:

- `requirements-base.txt`
- `requirements-dev.txt`

Operational notes:

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines and benchmark returns.

## Related Docs

- `docs/reference/strategies.md`
- `docs/adr/002-backtesting-layering.md`
