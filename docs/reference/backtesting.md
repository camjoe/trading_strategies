# Backtesting

Type: notes
Status: Active
Created: 2026-03-14
Last Reviewed: 2026-07-27
Purpose: Reference for backtesting commands, the backtest/optimization/walk-forward capability split, evaluation standards, and safeguards.
Related: [ADR 016 Optimizer Experiments as Research Evidence](../adr/016-optimizer-experiments-as-research-evidence.md), [Trading Package Map](../maps/trading-package-map.md), [Architecture Conventions](../architecture/architecture-conventions.md)

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

# Walk-forward optimization (see Optimize -> Promote Loop below)
python -m trading.interfaces.cli.main backtest-optimize --account momentum_5k --strategy trend --search-space '{"fast_window": [5, 10], "slow_window": [20, 30]}' --lookback-months 24

# Batch comparison
python -m trading.interfaces.cli.main backtest-batch --accounts momentum_5k,meanrev_5k --lookback-months 12

# Leaderboard
python -m trading.interfaces.cli.main backtest-leaderboard --limit 10
```

## Backtest Freshness (advisory)

Every strategy evaluation carries an advisory **backtest freshness** diagnostic:
the age of the experiment's holdout run (`backtest_runs.created_at`) measured
against the evaluation's generation time. When that age exceeds the stale
threshold (default **30 days**, `DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS` in
`trading.domain.backtest_freshness`) the diagnostic is flagged stale.

It is **advisory only** — it never blocks rotation or promotion and never
changes confidence or the blended score. It surfaces so operators can spot
evidence that has drifted far enough that re-running the optimizer is worth considering:

- CLI `report` / `compare-strategies`: a `backtest_age=<n>d (fresh|stale)`
  fragment on the evaluation summary line.
- CLI `promotion-status`: a `Backtest Freshness` line.
- Web: `backtestFreshness` on the evaluation detail payload and a `backtestStale`
  flag on the summary, shown in the promotion evidence grid and the compare view.

If stale evidence is later proven to skew decisions, this advisory is the hook
to tighten into confidence decay or a hard gate.

## Strategy Notes

- The full strategy catalog and its ids are documented in `docs/reference/strategies.md`.
- By default a backtest runs the account's active strategy — the default book's open assignment
  (ADR 014). Pass `--strategy` to backtest a specific strategy instead (e.g. a rotation challenger);
  rotation scores challengers through the same evidence path.
- Paper results before 2026-07-03 are not strategy evidence. Before the execution loop was closed,
  the paper trade path used a placeholder instead of strategy signals.

## Backtest, Optimization, Walk-Forward

A **backtest is the atomic unit**: a strategy over a date range, producing an equity curve and
trades. Everything else composes it — `run_backtest` is the primitive, and the optimizer invokes it
per training candidate, per OOS window, and once on the holdout, persisting a `backtest_runs` row for
each run it keeps. Optimizer-written rows *are* backtests; the `purpose` discriminator is what keeps
them distinguishable from standalone exploration.

Three capabilities, and the roles they play here:

| Capability | Question it answers | Role |
|---|---|---|
| `backtest` | Does the strategy run, fire trades, and make money over this period? | **Exploration and debugging.** The fast loop — use it to check signal logic and data before spending a sweep. Not promotion evidence (ADR 016). |
| `backtest-optimize` | Which parameters score best, *and does the tuning generalize?* | **Validation.** The slow loop, and the only source of research evidence. |
| Walk-forward | Does the tuning *process* hold up out-of-sample? | Not a separate command — an inherent property of `backtest-optimize`. |

Two deliberate choices follow. Optimization here **always** walks forward; plain grid search with no
out-of-sample validation is the classic overfitting generator and is not exposed. And a
walk-forward that optimizes nothing is just a segmented backtest — the weak cell in the grid, which
is why the rolling-window path was removed rather than kept as a cheaper option.

## Walk-Forward Terminology and Evaluation Standards

`backtest-optimize` is the only walk-forward path. A previous `backtest-walk-forward` command ran a
fixed strategy across chronologically shifted windows and grouped the results — **rolling-window
robustness testing**, not walk-forward optimization, since it never trained candidates on an earlier
interval, froze a winner, or used an untouched holdout. It was removed (revision `0027`) because
running `backtest-optimize` with a single-candidate search space reproduces it exactly and adds a
baseline comparison and a holdout.

The term **walk-forward optimization** applies only to a workflow meeting all of these conditions:

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
  candidate/eligible counts, the selected winner, and a rejection tally), the **compounded OOS
  series** (the per-window OOS returns compounded into one chronological series, since each window runs
  on an independently reset account; windows following a time gap — a step longer than the test window —
  are flagged, and the series is derived on read from the window rows, never stored), the
  **provenance manifest** (effective economics, book execution knobs, universe membership + lineage,
  provider/as-of, engine revision), and a **`Promotion gate: PASS`/`FAIL (<reasons>)` preview** (see
  below — computed by the same function `backtest-optimize-promote` checks, so the preview always
  matches what an actual promotion attempt will do). For a failed experiment, it instead prints the
  status, stage, and failure message — there is no winner/OOS/holdout/audit data to show.
- `backtest-optimize-promote <experiment_id> --key <new_key> [--no-freeze] [--allow-no-edge]` — mint a
  new tradeable `strategies` variant from the experiment's winner via `create_strategy_variant` (the
  winner params are validated against the base primitive), stamp provenance into its description, and
  record the audit link back to the experiment. The variant is **frozen by default** (evidence-backed →
  immutable); `--no-freeze` leaves it an editable draft. Being enabled, it is immediately a
  first-class catalog strategy available to rotation/assignment — no extra wiring closes the loop.

Promotion is **quality-gated by default** (`evaluate_promotion_gate` in
`backtesting/domain/optimization/promotion_gate.py`): beyond the existence/not-failed/not-already-promoted
checks, the winner must beat its own default on **all three** of — mean OOS return, a strict majority
of OOS windows (`oos_windows_beat_baseline > window_count / 2`; a good mean can mask a coin-flip
per-window record), and the untouched holdout return. Missing evidence on either side of any comparison
fails that condition — no evidence is not a pass. A failing gate raises with the specific reasons it
failed; `--allow-no-edge` bypasses the bar entirely (e.g. to prove the promotion mechanism works, or to
promote a deliberately weak strategy for testing) — the same escape hatch the machinery relied on before
this gate existed.

## Sweep Cost and the Candidate-Budget Ceiling

A sweep is not one backtest, it is `candidates x windows` training simulations plus a persisted OOS
run and a metrics-only baseline per window, plus the same pair once for the holdout. The candidate
count on its own understates the work badly: 8 candidates over 24 months of monthly windows is
already ~130 simulations.

Measured with `python -m scripts.benchmark_sweep` (re-run it after any change to the inner loop;
readings carry roughly ±20% run-to-run variance, so do not trust a single one):

| Universe | Per simulation | 8 cand x 13 win (132 sims) | 32 cand x 13 win (444 sims) |
|---|---|---|---|
| 12 tickers (default) | ~42 ms | 5.6 s | 20.0 s |
| 52 tickers | ~167 ms | — | 74 s |

Nearly all of that is the simulation loop. Everything a run reads before simulating — account, book,
universe, price history, benchmark — profiles at **0.2% of a run**, so caching or hoisting those
reads cannot pay off. Measure before optimising here; it has already been tried and reverted once on
the strength of a benchmark that could not resolve the effect.

**The UI route caps `candidateBudget` at 128** (`MAX_CANDIDATE_BUDGET` in
`apps/paper_trading_web/backend/schemas/strategy_lab.py`, default 32). `POST
/api/strategy-lab/optimizations` runs its sweep **synchronously**, so the request stays open for the
whole run; at the default geometry 128 is ~1,690 simulations, about 70 seconds on the default
universe and under five minutes on a wide one. The frontend estimates `candidates x windows` before
submitting and warns past 1,000 simulations.

That cap is derived from the measured per-simulation cost — revisit it whenever that cost moves, or
it becomes a limit on research rather than a guard on the request.

The ceiling belongs to the synchronous route, not to the optimizer. `backtest-optimize` on the CLI
takes an unbounded `--candidate-budget` because nothing is waiting on a socket — run large sweeps
there.

## Bar Data

The engine reads **whole daily bars**. `MarketDataProvider.fetch_bar_history` returns one frame per
ticker with `open/high/low/close/volume` (vocabulary in `trading.models.market_data.constants`), and
`backtesting/domain/bars.py` aligns them onto one calendar as a `BarPanel`. The live path reads the
same shape via `fetch_bar_histories`, so a strategy evaluates identically under backtest and in
runtime trading.

Three alignment rules, each chosen to avoid inventing data:

- **The calendar is the union** of every ticker's trading days, not the intersection, so one ticker
  going quiet cannot truncate the run for the rest.
- **On a day a ticker has no bar its prices carry forward and its volume is zero.** The last trade
  stays the best estimate of value; a carried-forward volume would assert trading that never
  happened, and any liquidity filter reading it would be reading an invention.
- **Days before a ticker's first bar stay empty.** Back-filling would fabricate prices from before
  the listing existed. The engine skips a ticker until it has a finite positive price
  (`_tradeable_price`) rather than trading on a missing one.

The aligned frames are what the simulation **prices and marks** at — it needs a value for every
holding on every bar. They are *not* what indicators are computed from; see below.

## Strategy Indicators

A strategy declares the series it reads as `IndicatorSpec` entries on its `StrategySpec`. The engine
computes each once per ticker per run and hands the signal an `IndicatorView` positioned at the bar
being decided: `view.value("fast_ma")` is today's value, `view.value("fast_ma", -1)` yesterday's.
Deriving indicators inside a signal instead would recompute the same rolling window on every bar to
read its last value.

- **Indicators are computed from each ticker's own bars** (`BarPanel.source`), then carried onto the
  shared calendar — never computed from the aligned frame. The shared calendar contains days a given
  ticker did not trade, and a rolling window over those carried-forward rows would make its
  indicators depend on *which other tickers are in the universe*: adding an unrelated name that
  trades on a day this one did not would move this one's moving average. Carrying values forward
  after the fact is not the same thing — it holds the value as of the ticker's last real bar, which
  is exactly what the live path computes from that same bar, so the two agree by construction.
  `build_signal_inputs` in `trading/domain/strategies/indicator_view.py` owns this.
- `view.bars()` counts *priced* bars, not calendar days, so a ticker whose history starts late
  reaches its minimum-history gate when it actually has the history — and a ticker that trades
  weekly is not credited with the daily calendar around it.
- An indicator names the bar column it reads. One sourced from a column the caller does not have
  raises by name, so a strategy cannot silently fall back to closes — which is what keeps backtest
  and live from diverging.
- Adding a kind means extending `INDICATOR_KIND_*` and `_compute` in
  `trading/domain/strategies/indicator_view.py`.

`breakout` uses this to compare the close against the prior window's true **high** and **low**, which
is what a Donchian breakout is defined on. Closing highs never exceed true highs, so measuring
against closes sets the threshold too low and fires on days that did not break out.

## Execution Order Within a Bar

A bar resolves in three phases: **evaluate every signal, then execute all sells, then execute buys.**
Deciding first keeps every signal a function of the same pre-trade state; selling before buying makes
the day's proceeds available to every buy rather than only to tickers later in the iteration.

When cash cannot fund every buy signal, `allocate_buy_quantities`
(`trading/domain/auto_trading_policy.py`) **scales the whole set proportionally**. A buy signal
carries no conviction — every "buy" on a bar is equally preferred, because that is all the strategy
said — so any ordering the engine picks is information the strategy never supplied. Proportional
scaling is order-independent by construction: each ticker's share depends only on its own request
and the total.

The runtime path faces the same problem with one trade per book per run, where proportional
allocation is not available. `order_signal_candidates` instead orders candidates by a hash of the
ticker and a per-run seed, so first pick spreads across names over runs while staying reproducible
within one.

Two consequences:

- Buys are sized against one **post-sell** portfolio equity, not an equity that drifts as earlier
  buys fill.
- A cash-constrained buy is **partially filled**, not dropped, and is logged as
  `signal=buy (cash-scaled)` so a shrunken position is not mistaken for a smaller signal.

## Safeguards and Approximation Notes

- Signals use prior-day data and execute on the next bar to reduce look-ahead bias.
- Daily adjusted bars are used; the intraday path within a bar is not modeled.
- Stop-loss and take-profit behavior is approximate when evaluated on daily bars. High and low are
  now available, so a level can be known to have been *reached*; the order in which the high and low
  occurred within the session still cannot be recovered.
- Equity is marked at closes, so reported max drawdown is a close-to-close figure and is optimistic
  against true intraday drawdown. This matters beyond reporting: the optimizer's `calmar_v1`
  objective divides by that drawdown, so the promotion gate reads the same flattered number.
- LEAPs mode is approximate and requires explicit opt-in (`--allow-approximate-leaps`).
- Survivorship bias can occur if ticker universes are based only on present-day symbols.

## Operating Notes

- Keep assumptions explicit (slippage, fees, execution timing).
- Prefer chronological validation with walk-forward windows.
- Compare against simple baselines, the strategy's existing default parameters, and benchmark returns.

## Related Docs

- `docs/reference/strategies.md`
- `docs/maps/trading-package-map.md`
- `src/trading/backtesting/README.md`
