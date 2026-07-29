# IBKR Paper Trading Runbook

Type: runbook
Status: Active
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Operator procedure for moving a book off the internal simulator onto real IBKR paper-account order mechanics, over either the Web API or the socket/TWS transport.
Related: [ADR 017: IBKR paper broker type](../adr/017-ibkr-paper-broker-type.md), [ADR 018: broker transport/venue matrix](../adr/018-broker-transport-venue-matrix.md), [Broker Integration Reference](../reference/broker-integration.md), [IBKR Client Portal Gateway Setup](../reference/broker-setup-ibkr.md), [Runtime Jobs Reference](../reference/runtime-jobs.md)

Procedure for pointing an account at a real IBKR **paper** account, replacing the in-process
`PaperBrokerAdapter` and its synchronous simulated fills.

## Which broker type to use

Transport and venue are independent — both transports support both venues
([ADR 018](../adr/018-broker-transport-venue-matrix.md)):

| `broker_type` | Transport | Needs `live_trading_enabled` | Account assertion |
|---|---|---|---|
| `paper` (default) | in-process simulator | no | none — never leaves the process |
| `interactive_brokers_web` | IBKR Web API | yes | none — operator-owned |
| `interactive_brokers_web_paper` | IBKR Web API | **no** | `account_id` must start with `DU` |
| `interactive_brokers_socket` | IBKR socket/TWS | yes | none — operator-owned |
| `interactive_brokers_socket_paper` | IBKR socket/TWS | **no** | every managed account must start with `DU` |

Any other non-empty value raises `UnknownBrokerTypeError`.

**Never reach IBKR paper by setting `live_trading_enabled = 1`.** That flag guards real money only.
Both paper venues connect without it and assert the account instead.

### Choosing a transport

- **Web API** (`interactive_brokers_web_paper`) — needs the Client Portal Gateway running and
  browser-authenticated. Its session expires and must be re-authenticated periodically.
- **Socket** (`interactive_brokers_socket_paper`) — needs TWS or IB Gateway running and logged in.
  Uses `broker_host` / `broker_port` / `broker_client_id` on the account row, so different accounts
  can hold different client ids against the same gateway.

Both are supported. If you have no strong preference, the Web API path has the longer history in
this repo; the socket path has the more complete client (snapshot quotes, structured rejections).

Whichever you pick, both reach **the same IBKR account** — same positions, same orders, same
statements. Only the local plumbing differs.

### "Client Portal" names two different things

Worth separating, because the collision causes real confusion:

- **Client Portal** (the website) — IBKR account management. Where you create the paper account, set
  market-data subscriptions, and view the account's orders. Shared by both transports.
- **Client Portal Gateway** (`clientportal.gw`) — a local Java proxy exposing IBKR's REST API on
  `https://localhost:5000`. **Web API path only.** The socket path never touches it; it uses TWS or
  IB Gateway on `7497` / `4002` instead.

The two also authenticate differently: the Client Portal Gateway holds a browser-established session
that expires and needs re-authentication, while TWS/IB Gateway stays logged in until its daily
forced restart.

IBKR restricts concurrent sessions per username, so running the Client Portal Gateway and TWS
against the same login simultaneously may disconnect one of them. Test that before depending on
having both available.

## What changes when you switch

The simulator accepts every order and fills it in full, instantly, at the requested price, with no
commission and no possibility of rejection or slippage. IBKR does none of that: orders come back
`SUBMITTED` and their executions arrive later.

The daily run handles the asynchrony. Steps `01` and `08` each reconcile outstanding broker fills
(`reconcile_orders`) before snapshotting equity, so the books absorb whatever the broker has
reported since the previous pass. A fill landing after the run's final reconciliation is picked up
by the next run's pre-trade pass. Consequences:

- **Run frequency starts to matter.** Under the simulator, one run a day settles everything. Against
  IBKR, positions and equity are only as current as your last run.
- **A run can end with orders still open.** That is normal, not a failure.
- Nothing cancels open orders when a run ends.

## Prerequisites

Both transports:

- [ ] IBKR paper account credentials (account id starts with `DU`)

Web API only:

- [ ] Client Portal Gateway installed, running, and authenticated — see
      [broker-setup-ibkr.md](../reference/broker-setup-ibkr.md)
- [ ] Private config prepared at `local/ibkr_web_api_config.json`, or the equivalent
      `TRADING_IBKR_WEB_API_*` environment variables

Socket only:

- [ ] TWS or IB Gateway installed and logged into the paper account
- [ ] API enabled (*Configure → Settings → API → Settings* → "Enable ActiveX and Socket Clients"),
      with "Read-Only API" **unchecked**
- [ ] Trusted IP `127.0.0.1` added, or the connection-confirmation dialog acknowledged
- [ ] A client id no other session uses — IBKR rejects duplicates

## Step 1 — Verify connectivity, read-only

Run before changing any account row. Neither check places orders or touches the database.

Web API:

```bash
.venv/Scripts/python.exe -m scripts.ibkr_web_api_smoke_test
```

Socket (TWS paper `7497`, TWS live `7496`, IB Gateway paper `4002`, IB Gateway live `4001`):

```bash
.venv/Scripts/python.exe -m scripts.ibkr_socket_smoke_test --port 7497 --client-id 99
```

Either way, confirm the reported account id starts with `DU` — if it does not, the factory will
refuse to connect in step 2. Add `--quote-tickers AAPL,MSFT` to the socket check to confirm
market-data permissions; select the alternative native backend with
`TRADING_IBKR_SOCKET_CLIENT_BACKEND=ibapi` (not installed by default).

### Optional — prove the order round trip

Reads succeeding does not prove that a submitted order can be *found again*, which is what fill
reconciliation depends on. Both smoke tests can place one non-marketable limit order, confirm it
comes back, and cancel it:

```bash
./.venv/bin/python -m scripts.ibkr_socket_smoke_test --port 4002 \
  --paper-order-check --paper-order-symbol AAPL --paper-order-limit-price 1.00
```

```bash
./.venv/bin/python -m scripts.ibkr_web_api_smoke_test \
  --paper-order-check --paper-order-symbol AAPL --paper-order-limit-price 1.00
```

Notes:

- **Use a clearly non-marketable limit price.** There is no default, deliberately: the point is an
  order that rests where it can be observed, not one that fills.
- The socket check refuses to submit unless every managed account is a `DU` paper account, since
  `--host` and `--port` could otherwise aim it at a live gateway.
- The order is cancelled afterwards. Cancellation is best-effort — outside market hours IBKR may
  hold an order pre-submission where a cancel is rejected. Pass `--skip-paper-order-cancel` to leave
  it resting; a DAY order expires at the close either way.
- `FAIL read back` is the result that matters. Reconciliation calls the same `get_open_trades()`, so
  an order it cannot see is an order whose fills would be stranded.
- This proves the broker half only. Applying fills to the books needs a database and an account row,
  so that half is exercised by the daily run in step 3.

## Step 2 — Point the account at IBKR paper

A manual database update. No migration is needed; `accounts.broker_type` is `TEXT NOT NULL` with no
CHECK constraint. `live_trading_enabled` stays `0` in both cases.

Web API — `broker_host` / `broker_port` / `broker_client_id` stay `NULL`, since the Web API path
does not read them:

```sql
UPDATE accounts
SET broker_type = 'interactive_brokers_web_paper'
WHERE name = 'momentum_5k';
```

Socket:

```sql
UPDATE accounts
SET broker_type = 'interactive_brokers_socket_paper',
    broker_host = '127.0.0.1',
    broker_port = 7497,
    broker_client_id = 11
WHERE name = 'momentum_5k';
```

Switch one account first. Leave the rest on `paper` until you trust the path.

## Step 3 — Run and verify

```bash
.venv/Scripts/python.exe -m trading.interfaces.runtime.jobs.daily.paper_trading --accounts momentum_5k --run-source manual
```

In `local/logs/daily_paper_trading_<date>_<time>.log`, check that:

- `Pre-trade reconcile fills` and `Post-trade reconcile fills` both report a count rather than
  raising
- the auto-trader line shows submissions rather than `Market closed`
- no `PaperBrokerAccountMismatchError` appears

Then confirm the orders reached IBKR. Both transports submit into the same account, so the Client
Portal website shows them either way; the TWS/Gateway order panel also shows them when that is what
you are running. Check symbols and quantities match.

To apply fills that arrive after a run has finished, without a full run:

```bash
.venv/Scripts/python.exe -m trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders --accounts momentum_5k
```

## Rolling back

```sql
UPDATE accounts
SET broker_type = 'paper'
WHERE name = 'momentum_5k';
```

Also clear the socket fields if you set them:

```sql
UPDATE accounts
SET broker_host = NULL, broker_port = NULL, broker_client_id = NULL
WHERE name = 'momentum_5k';
```

Cancel any still-open IBKR orders from the Client Portal or TWS first. Nothing in this repo cancels
them once the account stops pointing at IBKR, and the persisted `orders` rows will stay open because
no broker will report on them again.

## Switching transports

Both transports reach the same IBKR paper account, so switching is a `broker_type` change plus the
socket fields. What does *not* carry over is in-flight state: orders submitted over one transport
are still live at IBKR, but the persisted rows will only be reconciled by whichever transport the
account currently points at. Reconcile and settle before switching:

```bash
.venv/Scripts/python.exe -m trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders --accounts momentum_5k
```

Confirm no orders remain open, then change `broker_type`.

## Order lifecycle

**The broker expires orders, not this repo.** Orders are submitted with
`time_in_force = 'day'` (the default on `BookTradeIntent`; the `orders` table's CHECK allows only
`day` or `gtc`). IBKR cancels an unfilled DAY order at the close of the regular session. Nothing
here needs to — and deliberately does not — issue an end-of-run cancel sweep.

**What this repo can lose track of is its own rows.** IBKR's `/iserver/account/orders` covers the
current day. A DAY order that expired at a previous session's close simply stops being reported, so
reconciliation never sees it again and the persisted `orders` row would sit at `submitted`
indefinitely.

Reconciliation reports those rather than resolving them. An unreported order might have expired
unfilled, or might have filled on a day nothing ran — and marking a filled order cancelled would
silently corrupt the book. That call needs a human, so:

- `reconcile_orders` prints a `WARNING … not reported by the broker and left unresolved` line to
  stderr, naming each broker order id. The daily run captures stderr into its run log.
- The daily run artifact's step `07_submit_ibkr_orders` carries `stale_open_count` and a
  `stale_open` list — open orders carried over from an earlier session, per account.

### Resolving a stale open order

1. Look the order up in the Client Portal by its `broker_order_id`.
2. **If it never filled**, close the row:
   ```sql
   UPDATE orders SET status = 'cancelled', status_reason = 'expired unfilled at broker',
          updated_at = <now-iso> WHERE broker_order_id = '<id>';
   ```
3. **If it did fill**, do *not* hand-edit the row — the fill has to reach the book through
   `apply_book_fill` or positions, ledger, and equity will disagree. Capture the execution details
   and treat it as a data-repair task.

A steady trickle of stale orders means runs are too infrequent relative to submissions: reconcile
more often (`reconcile_orders` is cheap and safe to run on demand) rather than clearing rows by hand.

## Known gaps

- **Reconciliation is run-driven, not continuous.** There is no polling loop; fills land whenever the
  next run's reconcile step executes. An order filling minutes after a run stays unrecorded until the
  next one.
- **No automatic resolution of stale rows.** By design, per the section above.
- **The account assertion is not a capital guarantee.** It verifies the account *identifier*, not the
  gateway it reaches — see the Consequences section of [ADR 017](../adr/017-ibkr-paper-broker-type.md).
