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
- `IbkrSocketAdapter.get_order(broker_order_id)`. The base class returns `None`, so
  `open_order_reconciliation.py` cannot look up an order that `get_open_trades` omits, and a filled
  order may drop out of the open list. The `ib_async` client connects with only open orders and
  executions fetched, and `trades()` is served from that startup cache, so first confirm what a
  fill from an earlier session looks like after reconnect, then implement the lookup from that.
- Reconnect. `IbAsyncClient.connect` is one attempt with a 20 s timeout. A connection held across
  market hours needs a bounded reconnect with backoff that re-syncs `trades()` before trusting it,
  and fails loudly if the sync does not complete (an empty `trades()` looks like "no open orders").
- `check_broker_sessions` (`broker_preflight.py`) treats `OSError` and `RuntimeError` as unavailable,
  which covers a refused socket. Change its failure message, which tells the operator to start the
  Client Portal gateway, to name IB Gateway for socket accounts.
- Use a distinct client id for each connection that can be open at once (the daily job, the health
  check below, any manual script).

### 2. Replace the keepalive worker with a connection health check
`ibkr_session_keepalive` calls the Web API's `/tickle`; it has no purpose on the socket path. Replace
it with a worker that every few minutes connects, reads `managed_accounts()`, disconnects, and alerts
on a change of state, reusing the `SessionState` pattern and `notify_runtime_event`. Treat "refused"
as `unreachable` and "connected but no managed account" as `rejected`. Quiet outside the Monday
login window and after Friday close so a planned suspend sends no alert. Retire the Web API keepalive
unit and its tests in the same PR once the switch is done; keep the Web API adapter itself.

### 3. Host setup (runbook, no repo code)
- Install IB Gateway from IBKR's installer. Run it in the user's desktop session, autostarted.
- Settings: socket API enabled; trusted IP `127.0.0.1` only; read-only API off; paper port `4002`;
  Auto restart on, with the restart time outside IBKR's own maintenance window; never lock.
- Keep the host awake from Sunday night to Friday close: a user service holding
  `systemd-inhibit --what=sleep:idle`, started by a Sunday-evening timer with `WakeSystem=yes` and
  stopped by a Friday timer after 13:00 PT. Timers use the host's Pacific time. Laptop: also
  `HandleLidSwitch=ignore`. Fall back to masking the sleep targets for those days if the inhibitor
  does not hold.
- Weekly login: the owner logs in to IB Gateway on Sunday night, once the host is awake. The health
  check alerts if Gateway is still logged out at a set time before Monday's first run. Whether a
  Sunday-night login satisfies IBKR's weekly requirement through Friday close is UNVERIFIED; the
  trial week confirms it.
- Update `docs/runbooks/production-runtime-host.md` (Parts 5 and 6), `ibkr-operations.md`, and the
  transport guidance in `ibkr-paper-trading.md` to match.

### 4. Trial, then switch
1. Smoke test on the host against IB Gateway paper, including one fractional-size order.
2. Suspend the host over a weekend, wake it, and record whether Gateway needs a login.
3. Run one full week on a throwaway paper book using `interactive_brokers_socket_paper` and a market
   hours job; confirm fills reconcile and nothing double-posts.
4. Move the real book by changing `accounts.broker_type`, only with no open orders (in-flight orders
   do not carry across transports; see `ibkr-paper-trading.md`).

## Out of scope
Live trading, OAuth for the new Web API, third-party login automation, and removing the Web API
adapter.

## Done when
The trial week completes with no manual step except the one weekly login, reconciliation is clean, and
the runbooks describe the new host setup. Delete this plan in the PR that ships the work.

## Open questions for the owner
- What Sunday-night time should the host wake, and by what time must the login be done before the
  health check alerts?
- Should the weekend suspend stay, or is the machine simply left on all week once this works?
