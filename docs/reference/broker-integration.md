# Broker Integration Reference

Type: notes
Status: Active
Created: 2026-04-03
Last Reviewed: 2026-07-21
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
- legacy socket/TWS support boundaries

## Current Broker Paths

Broker resolution is handled in:

- `src/infrastructure/brokers/factory.py`

Supported `accounts.broker_type` values:

- `paper` (default)
- `interactive_brokers_web` (current/default live IBKR path)
- `interactive_brokers` (legacy socket/TWS path)

Key files:

- `src/trading/domain/broker_connection.py`: broker interface (`BrokerConnection`) and order models (`src/trading/models/orders/broker_order.py`)
- `src/infrastructure/brokers/paper_adapter.py`: paper execution adapter
- `src/infrastructure/brokers/ib_web/`: IBKR Web API package — `client.py` (HTTP client), `settings.py` (settings loader), `pacing.py` (pacing guard)
- `src/infrastructure/brokers/ib_web_adapter.py`: broker adapter backed by Web API client
- `src/infrastructure/brokers/legacy/factory.py`: legacy backend selector (`ib_async` vs `ibapi`)
- `src/infrastructure/brokers/legacy/ib_adapter.py`: legacy socket/TWS adapter
- `src/infrastructure/brokers/legacy/ib_client.py`: legacy client protocol + `IbAsyncClient` + `IbApiClient` stub
- `src/trading/repositories/orders.py`: persisted order state (clean book-keyed `orders`/`order_fills`; the submission + reconciliation paths write here — the legacy `broker_orders` repository was retired)

## Account Fields and Routing

Broker-related account fields:

| Field | Role |
|---|---|
| `account_kind` | account visibility/role (`managed`, `local`) |
| `broker_type` | execution backend selection |
| `broker_host` | legacy socket/TWS host |
| `broker_port` | legacy socket/TWS port |
| `broker_client_id` | legacy socket/TWS client id |
| `live_trading_enabled` | hard gate required for live broker adapters |

`account_kind` and `broker_type` are orthogonal:

- `account_kind` answers account role in this repo
- `broker_type` answers execution backend

## Live Trading Safety Guard

`live_trading_enabled` is a hard runtime gate for live broker paths.

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

## IBKR Web API Configuration

Primary integration path: `interactive_brokers_web`.

Settings loader:

- `src/infrastructure/brokers/ib_web/settings.py::load_ib_web_api_settings`

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

The shared order contract and `orders.status_reason` retain broker-provided rejection and
cancellation explanations when IBKR supplies one. The Web adapter reads
`order_status_description`; the legacy `ib_async` adapter reads the advanced rejection payload or
the latest structured order error. Later reconciliation polls without an explanation do not erase
a previously persisted reason.

## Legacy Socket/TWS Path

Legacy path remains available via `broker_type = 'interactive_brokers'`.

- default backend: `ib_async`
- optional backend: `ibapi` (native client stub currently not implemented)
- backend switch lives in `src/infrastructure/brokers/legacy/factory.py`

Legacy default socket ports:

- TWS paper: `7497`
- TWS live: `7496`
- IB Gateway paper: `4002`
- IB Gateway live: `4001`

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
