# IBKR Paper Trading Runbook

Type: runbook
Status: Active
Created: 2026-07-27
Last Reviewed: 2026-07-27
Purpose: Operator procedure for moving a book off the internal simulator onto real IBKR paper-account order mechanics, and the standing reason the socket/TWS path is not that route.
Related: [ADR 017: IBKR paper broker type](../adr/017-ibkr-paper-broker-type.md), [Broker Integration Reference](../reference/broker-integration.md), [IBKR Client Portal Gateway Setup](../reference/broker-setup-ibkr.md), [Runtime Jobs Reference](../reference/runtime-jobs.md)

Procedure for pointing an account at a real IBKR **paper** account, replacing the in-process
`PaperBrokerAdapter` and its synchronous simulated fills.

## Which broker type to use

Use **`interactive_brokers_paper`** (Web API / Client Portal Gateway). Per
[ADR 017](../adr/017-ibkr-paper-broker-type.md) it needs no `live_trading_enabled` flag and
positively asserts the configured account id is an IBKR paper account (`DU` prefix), failing closed
with `PaperBrokerAccountMismatchError` otherwise.

**Do not reach IBKR paper by setting `live_trading_enabled = 1` on a socket account.** ADR 017
considered and rejected exactly that: it conflates connectivity with capital risk, is forbidden for
automated processes, and leaves the configured account identity unverified.

| `broker_type` | Adapter | Needs `live_trading_enabled` | Account assertion |
|---|---|---|---|
| `paper` (default) | in-process simulator | no | none — never leaves the process |
| `interactive_brokers_paper` | IBKR Web API | **no** | `account_id` must start with `DU` |
| `interactive_brokers_web` | IBKR Web API | yes | none — operator-owned |
| `interactive_brokers` | IBKR socket/TWS | yes | none — operator-owned |

### On the socket/TWS path

The socket path (`ib_async`) is implemented and tested, but it has **no paper equivalent** — it
still requires `live_trading_enabled = 1`, which is the wrong flag for a paper account. ADR 017
leaves `interactive_brokers_socket_paper` as follow-up work, to be added only if the socket path
becomes the primary integration. Until that decision is made, use `interactive_brokers_paper`.

`scripts/ibkr_socket_smoke_test.py` remains available as a read-only connectivity diagnostic for the
socket path — see [Diagnosing the socket path](#diagnosing-the-socket-path).

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

- [ ] IBKR paper account credentials (account id starts with `DU`)
- [ ] Client Portal Gateway installed, running, and authenticated — see
      [broker-setup-ibkr.md](../reference/broker-setup-ibkr.md)
- [ ] Private config prepared at `local/ibkr_web_api_config.json`, or the equivalent
      `TRADING_IBKR_WEB_API_*` environment variables

## Step 1 — Verify connectivity, read-only

Run before changing any account row. It places no orders and does not touch the database:

```bash
.venv/Scripts/python.exe -m scripts.ibkr_web_api_smoke_test
```

This validates session/auth, account visibility, ledger, summary, and positions. Confirm the
reported account id starts with `DU` — if it does not, the factory will refuse to connect in step 2.

## Step 2 — Point the account at IBKR paper

A manual database update. No migration is needed; `accounts.broker_type` is `TEXT NOT NULL` with no
CHECK constraint.

```sql
UPDATE accounts
SET broker_type = 'interactive_brokers_paper'
WHERE name = 'momentum_5k';
```

`broker_host`, `broker_port`, and `broker_client_id` stay `NULL` — those are socket/TWS fields and
the Web API path does not read them. `live_trading_enabled` stays `0`.

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

Then confirm the orders reached IBKR — they should be visible in the Client Portal with matching
symbols and quantities.

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

Cancel any still-open IBKR orders from the Client Portal first. Nothing in this repo cancels them
once the account stops pointing at IBKR, and the persisted `orders` rows will stay open because no
broker will report on them again.

## Diagnosing the socket path

If you are investigating TWS/IB Gateway connectivity itself — separately from the question of which
broker type an account uses — this read-only check connects, fetches the account summary, positions,
and open trades, and disconnects. It places no orders and does not touch the database:

```bash
.venv/Scripts/python.exe -m scripts.ibkr_socket_smoke_test --port 7497 --client-id 99
```

Default ports: TWS paper `7497`, TWS live `7496`, IB Gateway paper `4002`, IB Gateway live `4001`.
Add `--quote-tickers AAPL,MSFT` to check market-data permissions. Select the alternative native
backend with `TRADING_IBKR_SOCKET_CLIENT_BACKEND=ibapi` (not installed by default).

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
