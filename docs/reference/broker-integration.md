# Broker Integration Reference

Type: notes
Status: Active
Created: 2026-04-03
Last Reviewed: 2026-07-24
Purpose: Define the current broker architecture, safety guardrails, and operator workflow for live and paper trading.
Related: [Runtime Operations Runbook](../runbooks/runtime-operations.md), [Service Cookbook](../architecture/service-cookbook.md)

## Purpose

Define the current broker architecture, safety guardrails, and operator workflow
for the Interactive Brokers Web API path.

## Scope

This document covers:

- broker-resolution behavior in runtime
- account fields that affect broker routing and live safety
- IBKR Web API private configuration and smoke-test workflow
- socket/TWS support boundaries

## Current Broker Paths

Broker resolution is handled in:

- `src/infrastructure/brokers/factory.py`

Supported `accounts.broker_type` values:

Transport (how IBKR is reached) and venue (whether real money can move) are independent
axes, so every transport has both venues — see
[`docs/adr/018-broker-transport-venue-matrix.md`](../adr/018-broker-transport-venue-matrix.md).

| Value | Transport | Requires `live_trading_enabled` | Account assertion |
|---|---|---|---|
| `paper` (default) | in-process simulator | no | none |
| `interactive_brokers_web` | IBKR Web API | yes | none (operator-owned) |
| `interactive_brokers_web_paper` | IBKR Web API | **no** | `account_id` must start with `DU` |
| `interactive_brokers_socket` | IBKR socket/TWS | yes | none (operator-owned) |
| `interactive_brokers_socket_paper` | IBKR socket/TWS | **no** | every managed account must start with `DU` |

Any other non-empty value raises `UnknownBrokerTypeError`. An absent or empty
`broker_type` still defaults to `paper`.

`paper` never leaves the process: `PaperBrokerAdapter` accepts every order and fills it
in full, immediately, at the requested price, with zero commission. It produces no
rejections, partial fills, or slippage, so its fill history is an accounting exercise
rather than execution evidence. Use one of the `_paper` IBKR types for anything intended
to generate real operational data.

Key files:

- `src/trading/domain/broker_connection.py`: broker interface (`BrokerConnection`) and order models (`src/trading/models/orders/broker_order.py`)
- `src/infrastructure/brokers/paper_adapter.py`: paper execution adapter
- `src/infrastructure/brokers/ibkr_web/`: Web API adapter, HTTP client, settings, and pacing
- `src/infrastructure/brokers/ibkr_socket/adapter.py`: backend-neutral socket/TWS adapter
- `src/infrastructure/brokers/ibkr_socket/contracts.py`: project-owned normalized client records
- `src/infrastructure/brokers/ibkr_socket/protocol.py`: socket client protocol
- `src/infrastructure/brokers/ibkr_socket/ib_async_client.py`: working `ib_async` backend
- `src/infrastructure/brokers/ibkr_socket/ibapi_client.py`: native `ibapi` connection, order,
  execution, commission, rejection, open-order, position, account-summary, and snapshot-quote
  callback state
- `src/infrastructure/brokers/ibkr_socket/factory.py`: socket backend selector
- `src/trading/repositories/orders.py`: persisted order state (clean book-keyed `orders`/`order_fills`; the submission + reconciliation paths write here — the legacy `broker_orders` repository was retired)

## Account Fields and Routing

Broker-related account fields:

| Field | Role |
|---|---|
| `account_kind` | account visibility/role (`managed`, `local`) |
| `broker_type` | execution backend selection |
| `broker_host` | socket/TWS host |
| `broker_port` | socket/TWS port |
| `broker_client_id` | socket/TWS client id |
| `live_trading_enabled` | hard gate required for the live venues (`interactive_brokers_web`, `interactive_brokers_socket`); not required for the `_paper` venues |

`account_kind` and `broker_type` are orthogonal:

- `account_kind` answers account role in this repo
- `broker_type` answers execution backend

## Live Trading Safety Guard

`live_trading_enabled` is a hard runtime gate for **real-money** broker paths.

- default is `0`
- live paths raise `LiveTradingNotEnabledError` from `infrastructure.brokers.factory` unless set to `1`
- this flag must be enabled manually by a human

Manual enable example:

```sql
UPDATE accounts
SET live_trading_enabled = 1
WHERE name = 'my-live-account';
```

The canonical guardrail rules live in
[`docs/architecture/architecture-conventions.md`](../architecture/architecture-conventions.md#live-trading-safety-guard).
This reference summarizes the runtime behavior; architecture conventions remain
the source of truth for what automated processes may and may not change.

### IBKR paper account guard

The `_paper` broker types reach the same gateways as their live counterparts without
`live_trading_enabled`, because no capital is at risk. They carry a different guard: the
resolved IBKR account must be a paper account (`DU` prefix), or the factory raises
`PaperBrokerAccountMismatchError` and refuses to connect.

Setting up a paper-executing book on the Web API:

```sql
-- No live_trading_enabled change required.
UPDATE accounts
SET broker_type = 'interactive_brokers_web_paper'
WHERE name = 'my-paper-account';
```

Then point the Web API settings at the paper account
(`TRADING_IBKR_WEB_API_ACCOUNT_ID=DU1234567`, or `account_id` in the private JSON
config). A live account id configured against this broker type fails closed.

The socket equivalent sets `broker_type = 'interactive_brokers_socket_paper'` plus the
`broker_host` / `broker_port` / `broker_client_id` fields, and takes its account identity
from IBKR rather than from configuration.

**The two transports assert at different moments.** The Web API knows its account id from
settings, so the assertion runs before connecting. The socket learns its account ids from
IBKR on connect, so the assertion runs after: a mismatch connects, fails, and disconnects
before returning. Connecting is not trading, so no order reaches a non-paper account
either way. The socket check requires *every* reported managed account to be a paper
account and treats an empty list as a failure — the session can trade any account it
manages.

Rationale: [`docs/adr/017-ibkr-paper-broker-type.md`](../adr/017-ibkr-paper-broker-type.md)
and [`docs/adr/018-broker-transport-venue-matrix.md`](../adr/018-broker-transport-venue-matrix.md).

## IBKR Web API Configuration

Primary integration path: `interactive_brokers_web`.

Settings loader:

- `src/infrastructure/brokers/ibkr_web/settings.py::load_ib_web_api_settings`

Resolution behavior:

- environment variables override file values
- optional file path override via `TRADING_IBKR_WEB_API_CONFIG`
- default local file path: `local/ibkr_web_api_config.json`

Important settings:

- `TRADING_IBKR_WEB_API_ACCOUNT_ID` (required)
- `TRADING_IBKR_WEB_API_BASE_URL`
- `TRADING_IBKR_WEB_API_HEADERS_JSON`
- `TRADING_IBKR_WEB_API_SESSION_TOKEN`
- `TRADING_IBKR_WEB_API_VERIFY_SSL`
- `TRADING_IBKR_WEB_API_TIMEOUT_SECONDS`
- `TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED`
- `TRADING_IBKR_WEB_API_KEEPALIVE_INTERVAL_SECONDS`
- `TRADING_IBKR_WEB_API_CONFIG` (path to private JSON config)

Recommended operator practice:

- keep account ids/tokens/cookies outside tracked repo files
- store secrets in env vars or an external private JSON file
- avoid committing credentials to account rows or fixtures

Private JSON example:

```json
{
  "account_id": "U1234567",
  "base_url": "https://localhost:5000/v1/api",
  "headers": {
    "Cookie": "api=replace-me-locally"
  },
  "verify_ssl": false,
  "timeout_seconds": 10,
  "keepalive_enabled": true,
  "keepalive_interval_seconds": 60
}
```

## Smoke Test Workflow

Script:

- `python -m scripts.ibkr_web_api_smoke_test`

Read-only smoke test validates:

- session/auth/account visibility
- ledger/summary/positions retrieval

Optional paper-order lifecycle check:

```sh
python -m scripts.ibkr_web_api_smoke_test \
  --paper-order-check \
  --paper-order-symbol AAPL \
  --paper-order-limit-price 1.00
```

Safety notes for optional paper-order check:

- use paper account only
- use clearly non-marketable limit prices
- cancellation is best-effort and status-dependent
- outside market hours, order states may remain pre-submission

## Runtime Order Lifecycle

Runtime execution opens one broker connection per account loop in:

- `src/trading/services/auto_trading/runtime.py`

Open-order reconciliation is handled by:

- `reconcile_open_broker_orders(...)`

Reconciliation behavior:

- polls open broker orders
- persists fill updates to clean book-keyed `orders` / `order_fills`
- applies fills through shared book accounting (`apply_book_fill`); account-level
  history derives from the fill rows — the `trades` table was retired in revision `0006`

The daily paper-trading job drives it via
`trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders`, once before the pre-trade
snapshot and again before the post-trade snapshot, so recorded equity always reflects the fills the
broker has reported so far. It is a no-op for `paper` accounts (synchronous fills, no open trades)
and load-bearing for the socket path.

The shared order contract and `orders.status_reason` retain broker-provided rejection and
cancellation explanations when IBKR supplies one. The Web adapter reads
`order_status_description`; the socket `ib_async` client reads the advanced rejection payload or
the latest structured order error. Later reconciliation polls without an explanation do not erase
a previously persisted reason.

## Socket/TWS Path

The socket path is available at both venues: `broker_type = 'interactive_brokers_socket'`
(real money, requires `live_trading_enabled = 1`) and
`broker_type = 'interactive_brokers_socket_paper'` (paper account assertion, no flag).

- default backend: `ib_async`
- optional backend: `ibapi` (orders, positions, account summaries, and snapshot quotes implemented)
- set `TRADING_IBKR_SOCKET_CLIENT_BACKEND=ibapi` to select the native client; unset or set it to
  `ib_async` for the default community client
- invalid backend values fail during broker construction instead of silently selecting a client

Default socket ports:

- TWS paper: `7497`
- TWS live: `7496`
- IB Gateway paper: `4002`
- IB Gateway live: `4001`

### Socket startup sync

`ib_async` serves `trades()`, `positions()`, and fill data from caches populated by a one-off
startup sync during `connect()` — nothing re-requests them later. By default that sync has a 4-second
budget and, on timeout, logs an error and connects anyway. IB Gateway routinely exceeds 4 seconds,
especially shortly after it starts.

A silently failed open-orders sync is not cosmetic: it leaves `trades()` empty in a way
reconciliation cannot distinguish from "no open orders", so fills would be stranded. `IbAsyncClient`
therefore connects with a longer timeout, `raiseSyncErrors=True`, and a `fetchFields` set trimmed to
the fields it actually reads (open orders and executions; positions are always fetched). Completed
orders and per-sub-account updates were dropped — never read, and each is another request that can
time out.

### Account identity over the socket

`IbkrSocketClient.managed_accounts()` reports the account ids the session can trade, which is
what `interactive_brokers_socket_paper` asserts on. `ib_async` exposes this as
`IB.managedAccounts()`; the native `ibapi` client captures the `managedAccounts` callback IBKR
sends on connect.

The previously deferred rename landed with ADR 018: `interactive_brokers` became
`interactive_brokers_socket` with no compatibility alias, since no account row used the old value.
The old string now raises `UnknownBrokerTypeError` rather than silently routing to the simulator.

## Extending Broker Support

When adding a new broker:

1. implement adapter under `src/infrastructure/brokers/`
2. add broker-type routing in `src/infrastructure/brokers/factory.py`
3. define the private config/env loading contract next to the adapter
4. update account `broker_type` constraints/docs
5. add tests under `tests/src/infrastructure/brokers/` and related runtime tests
6. add an operator setup guide only once the adapter has a real setup flow
7. update this document

## Related References

- `src/trading/README.md`
- `scripts/README.md`
- `docs/architecture/architecture-conventions.md`
- [`broker-setup-ibkr.md`](broker-setup-ibkr.md) — IBKR Client Portal Gateway operator setup checklist
- [`runbooks/ibkr-paper-trading.md`](../runbooks/ibkr-paper-trading.md) — operator procedure for moving a book onto real IBKR paper-account order mechanics
