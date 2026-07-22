# Backtesting

Type: notes
Status: Active
Created: 2026-03-14
Last Reviewed: 2026-07-22
Purpose: Reference for backtesting commands, walk-forward terminology, layering overview, and safeguards.
Related: [Trading Package Map](../maps/trading-package-map.md), [Architecture Conventions](../architecture/architecture-conventions.md)

Backtesting reuses account metadata from paper trading while storing run, trade, and equity history
in dedicated backtest tables. Package structure and layer ownership live in
`src/trading/backtesting/README.md` and `docs/maps/trading-package-map.md`.

Backtesting continues to use explicit SQL and the in-house engine because current needs are
analytics-heavy and query-shape specific. Revisit a framework or ORM only if object-graph
complexity, relationship tracking, or portability pressure materially increases.

## Commands

All backtesting commands use the shared trading CLI and accept `--help` for the full reference. They
assume the repository virtual environment created in the root README is active.

Create the database and apply the synthetic default account preset before the first run:

```sh
python -m scripts.data_ops.manage_db_migrations upgrade
python -m trading.interfaces.cli.main apply-account-preset --preset default
```

```sh
# Single backtest
python -m trading.interfaces.cli.main backtest --account momentum_5k --lookback-months 12

# Walk-forward
python -m trading.interfaces.cli.main backtest-walk-forward --account momentum_5k --start 2025-01-01 --end 2025-12-31 --test-months 1 --step-months 1

# Persisted walk-forward detail report
python -m trading.interfaces.cli.main backtest-walk-forward-report --account momentum_5k

# Batch comparison
python -m trading.interfaces.cli.main backtest-batch --accounts momentum_5k,meanrev_5k --lookback-months 12

# Leaderboard
python -m trading.interfaces.cli.main backtest-leaderboard --limit 10
```

## Scheduled Refresh

Recurring refreshes for persisted account backtests are handled by:

- `python -m trading.interfaces.runtime.jobs.daily.backtest_refresh`

Key behavior:

- **targeted, not blind** — refreshes only the stale or missing backtests across each account's
  rotation candidate strategies (incumbent + challenger schedule), driven by the freshness signal
  below (`--stale-threshold-days`, default 3)
- explicit opt-in via `--enable-run` or `DAILY_BACKTEST_REFRESH_ENABLED=1`
- duplicate same-day run guard unless `--force-run` is supplied
- transient retry handling for market-data failures
- machine-readable JSON artifacts under `local/exports/daily_backtest_refresh/`

For schedule/install details, see [runtime-jobs.md](runtime-jobs.md).

### Freshness cadence (advisory)

Every strategy evaluation carries an advisory **backtest freshness** diagnostic:
the age of the newest backtest run (`backtest_runs.created_at`) measured
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
  backtests each day.

Candidate strategy names are canonicalized through the strategy catalog, so an
aliased challenger (e.g. `macd_trend` → `macd`) matches its stored backtest and
is not re-run once fresh.

## Strategy Notes

- The full strategy catalog and its ids are documented in `docs/reference/strategies.md`.
- By default a backtest runs the account's active strategy — the default book's open assignment
  (ADR 014). Pass `--strategy` to backtest a specific strategy instead (e.g. a rotation challenger);
  the remediation flows use this to refresh challenger evidence.
- Paper results before 2026-07-03 are not strategy evidence. Before the execution loop was closed,
  the paper trade path used a placeholder instead of strategy signals.

## Walk-Forward Terminology and Evaluation Standards

The current `backtest-walk-forward` workflow executes a fixed strategy across chronologically shifted
test windows and groups the persisted results. This is **rolling-window robustness testing**, not full
walk-forward optimization: it does not train candidate parameter sets on an earlier interval, select
and freeze a winner, or evaluate the resulting process on an untouched final holdout.

Use **walk-forward optimization** only for a workflow that meets all of these conditions:

1. Every out-of-sample (OOS) window has a strictly earlier training interval.
2. Candidate parameters and the selection objective are declared before examining OOS results.
3. Ranking uses training evidence only, and the selected parameters are frozen before OOS execution.
4. OOS windows do not overlap when results are aggregated.
5. An untouched final holdout is excluded from training, selection, and preceding OOS windows.
6. Training, OOS, and holdout results are reported separately.

Point-in-time controls must account for indicator warm-up and external-data publication lag. Warm-up
observations may initialize calculations but must not contribute to scored metrics. External features
must use only values that would have been available at the simulated decision time; an embargo alone
does not correct revised or forward-looking data.

Optimization must not mutate canonical strategy parameters. Candidate search spaces, attempted
candidates, assumptions, effective parameters, universe membership, provider/as-of metadata, and
engine versions should be recorded well enough to audit how a winner was selected. Reports should
compare window stability and chronologically chain-linked OOS returns rather than summing independently
reset account equity values. Model fees and slippage on every candidate and disclose turnover so a
high-churn parameter set is not selected on gross returns, and compare a tuned winner against the
strategy's existing default parameters, not only the benchmark.

## Safeguards and Approximation Notes

- Signals use prior-day data and execute on the next bar to reduce look-ahead bias.
- Daily adjusted close data is used; intraday path is not modeled.
- Stop-loss and take-profit behavior is approximate when evaluated on daily bars.
- LEAPs mode is approximate and requires explicit opt-in (`--allow-approximate-leaps`).
- Survivorship bias can occur if ticker universes are based only on present-day symbols.

## Operating Notes

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with rolling or walk-forward windows.
- Compare against simple baselines, the strategy's existing default parameters, and benchmark returns.

## Related Docs

- `docs/reference/strategies.md`
- `docs/maps/trading-package-map.md`
- `src/trading/backtesting/README.md`
