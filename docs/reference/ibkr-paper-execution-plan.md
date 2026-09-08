# IBKR Paper Execution Plan

Type: notes
Status: Draft
Created: 2026-07-27
Last Reviewed: 2026-08-01
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

Audited 2026-07-27 against `develop`; re-verified 2026-08-01 against
`features/auto-trading-updates`. Where a later date appears below, that claim was checked
then.

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

**Repeat runs through the session are blocked, and intraday *data* is why.**
`domain/market_hours.py` holds a real NYSE calendar including holidays and early closes,
and `is_runtime_submission_window_open()` gates submission to regular hours. Repeat passes
through the trading day are the eventual goal, but they are not useful yet: no intraday
bars are fetched anywhere, so a second pass re-reads the same daily closes, cannot produce
a different signal, and would simply trade again on the identical evidence. The daily job's
duplicate-run guard is what stops that, and `--force-run` overrides it for a deliberate
operator re-run.

Fetching intraday bars is therefore the prerequisite for intra-session repeats, not an
independent nicety — relaxing the guard before that lands would buy extra trades rather
than extra information. The guard keys on the run's report date, so a replay of a past date
is unaffected.

**The optimizer works but is hand-driven.** Walk-forward optimization, the promotion
gate, and four migrations (`0021`–`0024`) exist and are reachable from three CLI
commands. No job, no schedule, no artifact history.

**The monitor could not read job output** — fixed in Phase 2.
`services/autonomy_monitor/artifacts.py` had looked for governance artifacts under
`local/exports/weekly_governance_*/` while the job runner writes them to
`local/artifacts/`, and read keys (`success`, `run_timestamp`, `steps`,
`min_required_successes`, `check_time`) that no producer emits. Its tests passed because
they asserted against fixtures written in the reader's imagined shape rather than real
job output — which is why the drift survived. A contract test in the daily-job suite now
feeds a real run artifact through the real reader, so the two cannot silently diverge
again.

## Phases

Ordered by dependency. Each phase should be independently valuable.

### Phase 1 — Separate IBKR paper connectivity from the real-money guard — **done**

Paper venues need no `live_trading_enabled`; they carry a positive assertion that the
resolved IBKR account is a `DU` paper account instead. See
[ADR 017](../adr/017-ibkr-paper-broker-type.md).

[ADR 018](../adr/018-broker-transport-venue-matrix.md) then made this symmetric across
transports: `interactive_brokers_web` / `interactive_brokers_web_paper` and
`interactive_brokers_socket` / `interactive_brokers_socket_paper`. The socket takes its
account identity from IBKR's on-connect `managedAccounts` report. `interactive_brokers`
was renamed with no alias, and an unrecognized `broker_type` now raises
`UnknownBrokerTypeError` instead of silently routing to the simulator.

### Phase 2 — One equity book on IBKR paper

**Code side done.** Two observability gaps closed:

- Steps `06_pretrade_risk_gate` and `07_submit_ibkr_orders` no longer skip. The gate and
  the submission still run inside the auto-trading runtime at step 05; these steps now
  report on the rows that work left behind — decisions by action, and orders by status
  with each rejection's `status_reason`. See `services/analysis/daily_report.py`.
- The `autonomy_monitor` reader was rewritten against the real artifact contract. It had
  been looking in `local/exports/weekly_governance_*/` for governance artifacts the runner
  writes to `local/artifacts/`, and reading `success`/`run_timestamp`/`steps` keys that no
  producer emits. Its tests passed because they asserted against invented fixtures, so a
  contract test now feeds a genuine run artifact through the real reader.

**Connectivity verified 2026-07-28** against IB Gateway paper over the socket transport:
connect, `managed_accounts()`, account summary, positions, `place_order()`, and — the one
that matters — `get_open_trades()` reading back a just-submitted order. That run also
found and fixed a real defect: `ib_async` gives its startup sync a 4-second budget and, by
default, logs a timeout and connects anyway, which would have left `trades()` empty in a
way reconciliation could not distinguish from "no open orders".

**Fill handling remains unproven.** Nothing has filled, so `_normalize_ib_async_fill`, the
`order_fills` writes, and `apply_book_fill` have still only run against fakes. That is
what the exit criterion below actually turns on, and it needs a real execution.

**Operator side remaining** — point a book at a paper venue. Either transport works; the
full procedure is in the [IBKR Paper Trading Runbook](../runbooks/ibkr-paper-trading.md).

```sql
UPDATE accounts SET broker_type = 'interactive_brokers_web_paper' WHERE name = '<book account>';
```

Then set `TRADING_IBKR_WEB_API_ACCOUNT_ID` to the `DU…` account (or `account_id` in
`local/ibkr_web_api_config.json`), start the Client Portal Gateway, and confirm with
`python -m scripts.ibkr_web_api_smoke_test` before the first run.

Exit criterion: a run artifact showing submitted orders with broker-assigned ids, and at
least one rejection or partial fill understood and explained.

### Phase 3 — Multiple equity books

Scale to the full set of equity books with distinct strategies, per-book caps, and
per-book NAV. Mostly configuration plus whatever Phase 2 exposes.

### Phase 4 — Intraday data

Two things are missing, and they have to land together. There is no reason for a later
pass to decide differently — no intraday bars, and no signal/indicator path that consumes
them — and the daily job's duplicate-run guard blocks a second pass precisely because a
pass with nothing new to read would only trade again on identical evidence.

So the guard is not a separate obstacle to remove first. Fetching intraday bars, teaching
the signal path to use them, and relaxing the guard are one change; doing the last of
those alone buys extra trades rather than extra information.

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
- `daily_snapshot` is **retired**. The daily run now reconciles and snapshots at both
  step `01` and step `08`, and its pre-submit gate refuses to trade on a snapshot that is
  missing or stale — so the run establishes its own equity baseline rather than depending
  on a separate job. The retired job's retry-with-backoff moved into
  `workflow.snapshot_account_with_retry`.
- Park the burn-in path rather than delete it. `burn_in_status` and the
  [burn-in protocol](../runbooks/burn-in-protocol.md) become load-bearing again in
  Phase 2+ once there is a real fill history to burn in, and before real capital.
- Do not expand the governance tier before Phase 3. Six weekly and monthly jobs review a
  system that is barely running, and four of the six have no working monitor consumer.

## Open Questions

- Which IBKR paper account and gateway configuration will Phase 2 use? Settings are
  operator-owned (`local/ibkr_web_api_config.json` or environment) and stay out of the
  repo.
- Does the risk gate behave sensibly against real rejections, or was it written assuming
  the simulator always fills? Unknown until Phase 2.
- Intraday bar source for Phase 4 is undecided; the current market-data provider path is
  daily-close oriented.
- Whether options execution goes through the Web API or the socket path. Both have a
  paper broker type since [ADR 018](../adr/018-broker-transport-venue-matrix.md), so this
  is now a question about options support on each transport rather than about venue
  plumbing.

## Related Docs

- [ADR 017: IBKR paper broker type](../adr/017-ibkr-paper-broker-type.md)
- [Broker Integration](broker-integration.md)
- [IBKR Client Portal setup](broker-setup-ibkr.md)
- [Runtime Jobs](runtime-jobs.md)
- [Burn-In Protocol](../runbooks/burn-in-protocol.md)
