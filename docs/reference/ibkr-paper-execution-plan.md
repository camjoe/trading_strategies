# IBKR Paper Execution Plan

Type: notes
Status: Draft
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Record the target shape of the multi-book auto-trader, the verified gap between that target and the current code, and the phase order for closing it.
Related: [ADR 017: IBKR paper broker type](../adr/017-ibkr-paper-broker-type.md), [Broker Integration](broker-integration.md), [Runtime Jobs](runtime-jobs.md), [Burn-In Protocol](../runbooks/burn-in-protocol.md)

## Purpose

The operator goal is a trader that runs multiple books with distinct strategies, trades
through the session rather than once a day, keeps optimizing, and can be watched. This
document records what of that exists today, what does not, and the order in which to
build the rest. It exists because the gap is larger and differently shaped than the
runtime job inventory suggests.

Read this before planning work on the runtime, the broker layer, or the job tier.

## Target

1. Multiple books, each running its own strategy, all live simultaneously.
2. Equity books at both ends of the risk spectrum.
3. Options books: an IV-focused book, and a book hunting put opportunities and risk in
   high-value options.
4. Trading through the session, not a single daily pass.
5. Strategies updated often from optimizer output.
6. Observable — an operator can confirm books are running and see their results.
7. Real capital within a few months.

## Verified Current State

Audited 2026-07-27 against `develop`.

**Nothing has traded for real, ever.** Every account resolves to `PaperBrokerAdapter`,
which accepts every order and fills it in full, immediately, at the requested price, with
zero commission. `get_positions()` and `get_account_info()` raise `NotImplementedError`.
There is no rejection, partial fill, slippage, or queue position anywhere in the
recorded history. Existing fill data cannot be used as execution evidence.

**Last runtime activity was 2026-05-03.** 19 daily paper-trading runs total; one daily
snapshot run (2026-03-26); two weekly backups (2026-03-18). `local/artifacts/` is empty,
so no governance job has ever produced an artifact.

**Books are real.** `services/books/` (`book_assignments`, `configuration`, `rotation`,
`sector_config`) plus `domain/book_accounting.py` support per-book strategy assignment,
rotation, and NAV. Books are the execution primitive per ADR 010 / ADR 014. Target items
1 and 2 are mostly configuration against existing infrastructure.

**Options do not exist.** This is the largest gap and it is structural, not incremental:

- `BrokerOrder` carries `ticker, side, qty, price, order_type, time_in_force`. There is
  no strike, expiry, right, or multiplier. `IbkrOrderRequest` is equally equity-only.
- There is no options chain data source, no implied volatility, and no greeks.
- `build_iv_rank_proxy` (`services/auto_trading/market.py`) computes the standard
  deviation of daily returns, annualizes it, and percentile-ranks it cross-sectionally.
  That is **realized** volatility. Despite the name it is not implied volatility and
  carries no options information.
- `interfaces/cli/commands/options.py` is argparse options, not financial options.

Target item 3 requires a contract model, chain data, an IV/greeks source, multi-leg
order support, options position accounting, and an options-aware risk gate. It is a
separate program, not a phase of this one.

**Intraday is blocked by the job model, not the market calendar.** `domain/market_hours.py`
holds a real NYSE calendar including holidays and early closes, and
`is_runtime_submission_window_open()` already gates submission to regular hours. But no
intraday bars are fetched anywhere, and the job tier keys idempotency on a day tag
(`day_tag`, `already_completed_today`). The dedup guard that protects the daily job is
exactly what would block a second run in the same session.

**The optimizer works but is hand-driven.** Walk-forward optimization, the promotion
gate, and four migrations (`0021`–`0024`) exist and are reachable from three CLI
commands. No job, no schedule, no artifact history.

**The monitor cannot read job output.** `services/autonomy_monitor/artifacts.py` looks
for governance artifacts under `local/exports/weekly_governance_*/`; the job runner
writes them to `local/artifacts/`. It reads keys `success`, `run_timestamp`, `steps`,
`duration_seconds`, `min_required_successes`, and `check_time`; the jobs write `status`,
`started_at`/`finished_at`, `step_results`, `completed_steps`, `min_consecutive_days`,
and `generated_at`. Its tests pass because they assert against fixtures written in the
reader's imagined shape rather than real job output. Target item 6 is unmet and currently
reports false negatives.

## Phases

Ordered by dependency. Each phase should be independently valuable.

### Phase 1 — Separate IBKR paper connectivity from the real-money guard

Add `broker_type = 'interactive_brokers_paper'`: same Web API adapter, no
`live_trading_enabled` requirement, and a positive assertion that the configured
`account_id` is a `DU` paper account. See [ADR 017](../adr/017-ibkr-paper-broker-type.md).

Nothing else in this plan can produce real execution data until this lands.

### Phase 2 — One equity book on IBKR paper

Point a single book at `interactive_brokers_paper` and let the daily cycle run against
real order mechanics. Two supporting changes:

- Un-skip DAG steps `06_pretrade_risk_gate` and `07_submit_ibkr_orders`. They are
  currently skipped with the reason that the work happens inside the auto-trading
  runtime — true, but it means the run artifact reports nothing about submission.
- Fix the `autonomy_monitor` artifact contract so the run is observable.

Exit criterion: a run artifact showing submitted orders with broker-assigned ids, and at
least one rejection or partial fill understood and explained.

### Phase 3 — Multiple equity books

Scale to the full set of equity books with distinct strategies, per-book caps, and
per-book NAV. Mostly configuration plus whatever Phase 2 exposes.

### Phase 4 — Intraday cadence

Replace the day-tagged job model: intraday bars, a per-slot idempotency key rather than
per-day, and a runner that fires repeatedly through the session. This is where the job
tier is reworked, so avoid investing in daily-cadence job structure before it.

### Phase 5 — Optimizer on a schedule

Give the walk-forward loop a job so candidate quality accumulates a history.

### Phase 6 — Options program

Contract model, chain data, IV and greeks, multi-leg orders, options accounting, and an
options-aware risk gate. Sized and planned separately once equity execution is proven.

## Consequences for the job tier

The job inventory was built for a system that runs a known-good strategy unattended and
proves it safe to go live. That is the right eventual shape, but most of it currently
guards activity that is not happening.

- Keep `paper_trading`, `trader_health`, `weekly_db_backup`.
- Retire `daily_snapshot`: it runs the same per-account snapshot command as DAG step
  `08_reconcile_fills_update_ledgers`, is disabled by default, and has run once.
- Park the burn-in path rather than delete it. `burn_in_status` and the
  [burn-in protocol](../runbooks/burn-in-protocol.md) become load-bearing again in
  Phase 2+ once there is a real fill history to burn in, and before real capital.
- Do not expand the governance tier before Phase 4. Six weekly and monthly jobs review a
  system that is not running, and four of the six have no working monitor consumer.

## Open Questions

- Which IBKR paper account and gateway configuration will Phase 2 use? Settings are
  operator-owned (`local/ibkr_web_api_config.json` or environment) and stay out of the
  repo.
- Does the risk gate behave sensibly against real rejections, or was it written assuming
  the simulator always fills? Unknown until Phase 2.
- Intraday bar source for Phase 4 is undecided; the current market-data provider path is
  daily-close oriented.
- Whether options execution goes through the Web API or the socket path — the socket
  path has no paper broker type today.

## Related Docs

- [ADR 017: IBKR paper broker type](../adr/017-ibkr-paper-broker-type.md)
- [Broker Integration](broker-integration.md)
- [IBKR Client Portal setup](broker-setup-ibkr.md)
- [Runtime Jobs](runtime-jobs.md)
- [Burn-In Protocol](../runbooks/burn-in-protocol.md)
