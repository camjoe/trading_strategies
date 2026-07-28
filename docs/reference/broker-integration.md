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

| Value | Adapter | Requires `live_trading_enabled` | Account assertion |
|---|---|---|---|
| `paper` (default) | in-process simulator | no | none |
| `interactive_brokers_paper` | IBKR Web API | **no** | `account_id` must start with `DU` |
| `interactive_brokers_web` | IBKR Web API | yes | none (operator-owned) |
| `interactive_brokers` | IBKR socket/TWS | yes | none (operator-owned) |

`paper` never leaves the process: `PaperBrokerAdapter` accepts every order and fills it
in full, immediately, at the requested price, with zero commission. It produces no
rejections, partial fills, or slippage, so its fill history is an accounting exercise
rather than execution evidence. Use `interactive_brokers_paper` for anything intended to
generate real operational data.

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
| `live_trading_enabled` | hard gate required for real-money broker adapters; not required for `interactive_brokers_paper` |

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

`interactive_brokers_paper` reaches the same Client Portal gateway without
`live_trading_enabled`, because no capital is at risk. It carries a different guard: the
resolved `account_id` must be an IBKR paper account (`DU` prefix), or the factory raises
`PaperBrokerAccountMismatchError` and refuses to connect.

Setting up a paper-executing book:

```sql
-- No live_trading_enabled change required.
UPDATE accounts
SET broker_type = 'interactive_brokers_paper'
WHERE name = 'my-paper-account';
```

Then point the Web API settings at the paper account
(`TRADING_IBKR_WEB_API_ACCOUNT_ID=DU1234567`, or `account_id` in the private JSON
config). A live account id configured against this broker type fails closed.

Rationale: [`docs/adr/017-ibkr-paper-broker-type.md`](../adr/017-ibkr-paper-broker-type.md).

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

The socket path remains available via `broker_type = 'interactive_brokers'`.

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

### Deferred persisted-name migration

Code and package names use `ibkr_socket`; the database still stores
`broker_type = 'interactive_brokers'` for compatibility. A later migration should:

1. add `interactive_brokers_socket` to the account constraint;
2. rewrite existing `interactive_brokers` rows to `interactive_brokers_socket`;
3. accept the old value temporarily as a factory alias if external configuration still uses it;
4. update account-profile fixtures and operator configuration;
5. remove the compatibility alias only after a repository-wide usage check and migration validation.

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
