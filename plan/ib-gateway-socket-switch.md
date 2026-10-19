# Plan: move IBKR paper trading to IB Gateway and the socket adapter

Status: drafted 2026-10-16. Not started. Nothing below has been run on the host.
Branch to use: `feature/ib-gateway-socket-switch`, off `develop`.
Not for the unattended `implement-plan` pickup: it edits guarded paths (broker, runtime-job, and
`scripts/` prefixes), so those commits would be held. Implement it in a session.

## Decisions (owner, 2026-10-16)
- Use IB Gateway with the existing socket adapter (`interactive_brokers_socket_paper`), not the Client
  Portal Gateway and Web API.
- Use only IBKR's own mechanisms. No third-party login automation (IBC, IBeam, IBAutomater).
- Keep the Linux host awake from Sunday night, when the owner logs in to IB Gateway, until the
  market closes on Friday. The host's time zone is Pacific, so Friday's 16:00 ET close is 13:00 PT.
  It may suspend between Friday's close and Sunday night.
- The job may later run for most of market hours, not one block, so the connection must survive a
  long session and a broker disconnect.

## Why
The Web API session expires within minutes of no tickle and its gateway has no official unattended
re-login, so a long idle gap or a suspend always needs a manual browser login. IBKR's documented route
for API users is TWS or IB Gateway with its own auto-restart: a daily restart without a login, and a
manual login about once a week. The socket adapter is already built and was smoke-tested on IB Gateway
paper on 2026-07-28 (outside market hours).

## What is known vs unverified
Known from the repo: the adapter, factory routing, the `DU` paper assertion, and the smoke test
(`python -m scripts.ibkr_socket_smoke_test --port 4002 --client-id 99`).

From web-search summaries of IBKR's documentation (the pages returned 403 to the fetch tool, so they
were not read in full). Re-check each on the host or in a browser before relying on it:
- IBKR documents a manual login in the Gateway or TWS login window, and does not support a headless
  Gateway. The host therefore needs a display session; it is a desktop machine, so this fits.
- IBKR's auto-restart restarts the application daily without a login and needs a manual login about
  once a week, around the weekend. The exact weekly day and time, and the restart-time setting, are
  UNVERIFIED.
- The TWS API limit is 50 orders per second. Not a concern at this volume.

UNVERIFIED, decided by the trial below:
- Whether IB Gateway is still logged in after the weekend suspend (assume not: the Sunday-night
  login is a fresh login).
- Whether the paper login shares a username with anything else. IBKR allows one session per
  username; stop the Client Portal Gateway before logging in IB Gateway if they share one.
- Whether the socket path accepts fractional share sizes. The books size equity orders in 0.0001
  steps (`FRACTIONAL_SHARE_STEP`); the 2026-10-09 rejections were on the Web API, and the socket path
  has not been exercised with a fractional size. This gates the switch.
- Whether a systemd sleep inhibitor stops the desktop's idle suspend on this host.

## Work

### 1. Socket adapter gaps (code, tests)
- DONE in code, UNVERIFIED on a Gateway: `IbkrSocketAdapter.get_order` and
  `IbkrSocketClient.find_trade`. `get_open_trades` already returns every trade the connection knows,
  so the gap was an order that filled while no job was connected: `ib_async` keeps its execution in
  `fills()` attached to no trade, so `trades()` omits it. `find_trade` rebuilds it from the
  executions (matched on order id and client id) plus the completed order (matched on permId, via
  `reqCompletedOrders`). Covered by unit tests with a fake backend only. Confirm on the host:
  place a market order, disconnect before the fill is read, reconnect, and check `get_order` returns
  it with its fills. IBKR reports completed orders for the current day only, so an order from an
  earlier day stays unreported. The native `ibapi` backend returns `None`.
- DONE: the preflight failure message names IB Gateway as well as the Client Portal Gateway.
- DONE: a bounded connect retry in `IbkrSocketAdapter.connect` (three attempts, pauses of 5 s and
  15 s, only for `OSError`: refused, timed out, sync error). Nothing in the repo holds a broker
  connection open: the daily run connects, uses and disconnects for each phase, and every connect
  re-syncs `trades()` and fails loudly if the sync does not complete. Reconnecting a connection held
  across market hours has nothing to attach to until a job is designed to hold one; decide that
  before building it (a drop mid-use today surfaces as "not connected" on the next call).
- `check_broker_sessions` (`broker_preflight.py`) treats `OSError` and `RuntimeError` as unavailable,
  which covers a refused socket. Change its failure message, which tells the operator to start the
  Client Portal gateway, to name IB Gateway for socket accounts.
- Use a distinct client id for each connection that can be open at once (the daily job, the health
  check below, any manual script).

### 2. Replace the keepalive worker with a connection health check
DONE in code, UNVERIFIED on a Gateway: `maintenance/ibkr_gateway_health.py`. Every
`--interval-seconds` (default 300) it connects to the API port with `--client-id` (default 901),
reads `managed_accounts()` and disconnects, and alerts when a failure has lasted `--grace-seconds` (default 900, so the Gateway's nightly restart passes
quietly) and again on recovery; every change of state is logged at once. Refused or timed out is
`unreachable`; connected with no account, or a `RuntimeError`, is `rejected`; a start with the Gateway
still down after the grace period alerts, which is the Sunday-night login reminder. Each check is a full
client connect with the startup sync, so a slow Gateway can fail one; the grace period absorbs that. Client
id 901 is not checked against the accounts' `broker_client_id`; record it as reserved in the runbook. It has no schedule of its own: the host starts it
with the Sunday timer and stops it after Friday's close, so a planned suspend sends no alert.
The Web API `ibkr_session_keepalive` worker and its tests are retired; the Web API adapter and client stay.

### 3. Host setup (runbook, no repo code)
DONE as text, UNTESTED on the host: Part 6 of `docs/runbooks/production-runtime-host.md` (IB Gateway
settings, the Sunday-to-Friday awake window as system units with a sleep inhibitor, the health unit,
reserved client ids, switching from the Client Portal Gateway, and the first-week checks that settle the
UNVERIFIED items) and a socket section in `docs/runbooks/ibkr-operations.md`. The transport guidance in
`ibkr-paper-trading.md` was not touched: that file is not valid UTF-8 and the edit tools refuse it.
The old Part 6 of the host runbook (the Client Portal units) and the Client Portal text in the operations and
paper-trading runbooks are retired; `broker-setup-ibkr.md` stays as the Web API adapter's checklist.
Remaining: run the units on the host, switch the account row, remove the old user units, and record the
answers in the private checklist. Merge only after the host account is switched, or the old keepalive
service will fail every 30 seconds.

### 4. Trial, then switch
1. Smoke test on the host against IB Gateway paper. `--fill-lookup-check` (built, tested with fakes only) fills a
   small market order, reconnects, and checks `get_order`; give it a fractional `--fill-order-qty` to test that too.
2. Suspend the host over a weekend, wake it, and record whether Gateway needs a login.
3. Run one full week on a throwaway paper book using `interactive_brokers_socket_paper` and a market
   hours job; confirm fills reconcile and nothing double-posts.
4. Move the real book by changing `accounts.broker_type`, only with no open orders (in-flight orders
   do not carry across transports; see `ibkr-paper-trading.md`).

## Held connection (design only, nothing built)

Owner decision 2026-10-17: a connection held open through market hours is intended.

### What the code does today, and what constrains the design
- Every phase connects, works and disconnects, through the `broker_factory(account)` seam
  (`get_broker_for_account`): the preflight in the orchestrator process, then the pre-trade reconcile,
  each auto-trader group and the post-trade reconcile, each in its own subprocess
  (`workflow.py`, `stream_command`). A connection cannot be shared across those processes.
- The daily run is one pass per day. The duplicate-run guard blocks a second pass on purpose, because
  no intraday data exists yet and a repeat pass would trade on identical evidence
  (`docs/reference/ibkr-paper-execution-plan.md`, Phase 4). Holding a connection does not change that.
- Consequence: a held connection needs one long-running process that owns the connection and runs the
  passes in-process. It is a new job, not a change to the daily batch's subprocess steps.

### What holding buys
- `trades()` and `fills()` stay live, so reconciliation reads current state with no startup sync and no
  `find_trade` lookup for same-day fills.
- No reconnect churn, and no window in which a restarting Gateway refuses the connect.
- It buys nothing for decisions until Phase 4 (intraday data) exists. Do not build the loop job before
  that is decided.

### Proposed shape
DONE in code (`infrastructure/brokers/session.py`, tested with fakes only): the session and lease. The
job that uses them is not built.
- `BrokerSession` in `infrastructure/brokers/ibkr_socket/`: owns one adapter, connects through the same
  retry, and on each `lease()` checks `is_connected()` and reconnects if the connection dropped.
  Every (re)connect re-runs the paper assertion (`managed_accounts()`), never only the first.
- The lease is an adapter-shaped object whose `disconnect()` does nothing, so existing code that calls
  `broker_factory(account)` and `broker.disconnect()` in a `finally` works unchanged. The owner calls
  `session.close()` at shutdown. The session's `lease` is passed as `broker_factory` at the job's
  composition seam; no service changes.
- The session keeps a connection only while the account row's broker settings and `live_trading_enabled`
  match those it connected with, so turning the live flag off stops the next lease. Leases from before a
  reconnect, or after `close()`, raise. The job must pass a freshly read account row to every lease.
  UNVERIFIED: whether the Gateway refuses a same-client-id reconnect right after a drop; the connect
  retry may absorb it.
- A drop mid-call surfaces as the existing "not connected" error and, for submission, the
  `broker_api_anomaly` kill switch. An order sent just before a drop is recovered by the existing
  pending-row adoption on `orderRef` at the next reconcile.
- The Gateway's own daily restart drops the connection outside market hours. The session reconnects on
  the next `lease()`; the job ends at the close, so no held connection spans a restart.
- The connection-health worker (Work item 2) is a separate process with its own client id.

### Open questions (decide before building)
- Client ids. IB allows one connection per client id, so while the held session owns the account row's
  `broker_client_id`, the operator CLIs (`reconcile_orders`, the smoke test) and the health worker
  would be refused or would kick the session. UNVERIFIED which happens. Proposal: operator tools and
  the health worker take a distinct id from an environment override, documented in the runbook.
- Process model: a long-running service started Sunday night and stopped at Friday's close, or a
  scheduler-run job that loops only inside the submission window. The first matches the weekly login
  rhythm; the second reuses the job runner, its sentinel and its alerts.
- Whether to build the session and lease first, with the health worker, and defer the loop job until
  Phase 4 lands. Recommended: the primitive is small and testable with the fake client; the loop is
  not worth building without intraday data.

## Out of scope
Live trading, OAuth for the new Web API, third-party login automation, and removing the Web API
adapter.

## Done when
The trial week completes with no manual step except the one weekly login, reconciliation is clean, and
the runbooks describe the new host setup. Delete this plan in the PR that ships the work.

## Open questions for the owner
- Decided: after a mid-week reboot the owner restarts the awake window by hand with one command
  (`sudo systemctl restart trading-awake.service`), documented in the host and operations runbooks. Nothing starts it at boot.
- Deferred: a fill rebuilt by `get_order` carries commission 0 unless IBKR sent the commission report during
  the startup sync, and exec-id dedup then keeps the real figure out. Decide after the host trial prints each
  fill's commission and shows whether IBKR paper reports any.
- Deferred: two held accounts on one Gateway with the same `broker_client_id` would collide. Nothing holds
  two connections at once today, so it cannot happen until the loop job exists; decide then.
- What Sunday-night time should the host wake, and by what time must the login be done before the
  health check alerts?
- Should the weekend suspend stay, or is the machine simply left on all week once this works?
