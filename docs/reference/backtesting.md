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
compare window stability and chronologically compounded OOS returns rather than summing independently
reset account equity values. Model fees and slippage on every candidate and disclose turnover so a
high-churn parameter set is not selected on gross returns, and compare a tuned winner against the
strategy's existing default parameters, not only the benchmark.

## Optimize → Promote Loop

The `backtest-optimize` command runs the full walk-forward optimization (grid search per training
window → freeze the winner → OOS + untouched holdout) and **persists one `optimization_experiments`
row** per run, printing its id. That row is Tier-1 persistence: the run config, the forward-carried
winner parameters (the promotion candidate), a small OOS aggregate (mean winner/baseline return and
how many windows the winner beat the default), the untouched-holdout summary, and — once promoted —
the link to the resulting catalog variant.

Each run also persists the **per-window and per-candidate audit trail** (revision `0022`): one
`optimization_windows` row per walk-forward window (its train/test boundaries and a link to the
window's persisted winner OOS `backtest_runs` row) and one `optimization_trials` row per evaluated
grid candidate (canonical params + hash, objective value/components, eligibility + rejection reason,
and the `selected` winner flag). This is the multiple-testing control — every attempted candidate is
recorded, not just the winner — and the window link also closes the earlier gap where per-window OOS
runs were written but not tied back to their experiment. Experiment, windows, and trials are written
in one transaction, and deleting an experiment cascades to its windows and trials.

Each run also freezes one **provenance manifest** (`optimization_run_manifests`, 1:1, revision `0023`):
the effective economics (initial cash, benchmark, slippage, fee), the book's effective risk/sizing
knobs, the exact resolved universe membership + lineage, the market-data provider + an as-of timestamp,
and the engine/source revision — the assumptions every candidate in the experiment shared. It is a
**provenance and audit record, not a replay guarantee** (no input price payloads are stored), and it
deliberately *freezes* (copies) the effective values rather than linking, so later edits to the book or
account cannot rewrite what a past run assumed. It is written in the same transaction and cascades with
the experiment.

**Fail-fast experiment state (revision `0024`):** the account and strategy are resolved *before* any
backtest runs, so an unknown account/strategy fails immediately rather than after a full optimization
run. If the window-search or holdout stage raises instead — a market-data/DB error, or the *expected*
"no eligible candidate" outcome for a training window — the run persists exactly one
`optimization_experiments` row with `status='failed'`, `failure_stage` (`window_search` or `holdout`),
`failure_message`, and `window_count` set to however many windows completed first. This is deliberately
minimal: no `optimization_windows`/`optimization_trials`/manifest rows are written for a failed
experiment (no partial audit tree), and any `backtest_runs` rows the completed windows already wrote
remain unlinked, same as any other historical run. The CLI error message references the persisted
experiment id so the attempt can be inspected via `backtest-optimize-show`.

Two follow-on commands operate on a stored experiment:

- `backtest-optimize-show <experiment_id>` — print the stored config, winner params, OOS aggregate,
  holdout evidence, promotion status, the per-window audit (each window's boundaries + OOS run, its
  candidate/eligible counts, the selected winner, and a rejection tally), and the **compounded OOS
  series** (the per-window OOS returns compounded into one chronological series, since each window runs
  on an independently reset account; windows following a time gap — a step longer than the test window —
  are flagged, and the series is derived on read from the window rows, never stored), and the
  **provenance manifest** (effective economics, book execution knobs, universe membership + lineage,
  provider/as-of, engine revision). For a failed experiment, it instead prints the status, stage, and
  failure message — there is no winner/OOS/holdout/audit data to show.
- `backtest-optimize-promote <experiment_id> --key <new_key> [--no-freeze]` — mint a new tradeable
  `strategies` variant from the experiment's winner via `create_strategy_variant` (the winner params
  are validated against the base primitive), stamp provenance into its description, and record the
  audit link back to the experiment. The variant is **frozen by default** (evidence-backed →
  immutable); `--no-freeze` leaves it an editable draft. Being enabled, it is immediately a
  first-class catalog strategy available to rotation/assignment — no extra wiring closes the loop.

Promotion's gate is **operational completeness only**: the experiment must exist, must not have
`status='failed'` (a failed run has no winner to promote), and must not already be promoted (one
promotion per experiment keeps the link 1:1). It does **not** require an out-of-sample edge — a tuned
winner that failed to beat its own default is still promotable, with its recorded OOS/holdout evidence
left for the operator to judge. This makes the machinery exercisable end to end (including on a
deliberately weak strategy) before any real edge exists.

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
