# Broker Integration Notes

## Overview

The broker layer provides a uniform interface over paper and live broker connections.
All order submission, fill tracking, and account data flows through this abstraction —
the rest of the trading engine never touches a broker SDK directly.

---

## Architecture

```
auto_trader_runtime_service
        │
        ▼
trading/brokers/factory.py          ← resolves BrokerConnection for an account
        │
        ├── PaperBrokerAdapter       ← default; immediate fills, zero commission
        │
        ├── InteractiveBrokersAdapter
                │
                └── IBClientProtocol (injected)
                        ├── IbAsyncClient   ← wraps ib_async (default, recommended)
                        └── IbApiClient     ← wraps IBKR native ibapi (stub)
        │
        └── InteractiveBrokersWebAdapter
                │
                └── InteractiveBrokersWebClient
                        └── IBKR Client Portal / Campus Web API
```

### Key files

| File | Purpose |
|------|---------|
| `trading/brokers/base.py` | `BrokerConnection` ABC, `BrokerOrder`, `OrderFill`, `OrderStatus` |
| `trading/brokers/paper_adapter.py` | Simulated immediate-fill paper broker |
| `trading/brokers/ib_adapter.py` | Interactive Brokers live adapter |
| `trading/brokers/ib_client.py` | `IBClientProtocol` + `IbAsyncClient` + `IbApiClient` stub |
| `trading/brokers/ib_web_adapter.py` | Interactive Brokers Web API live adapter |
| `trading/brokers/ib_web_client.py` | Web API config loader + HTTP client |
| `trading/brokers/factory.py` | Routes accounts → correct `BrokerConnection` |
| `trading/repositories/broker_orders_repository.py` | DB persistence for orders and fills |
| `trading/services/auto_trader_runtime_service.py` | Wires broker into trade execution loop |

---

## Account configuration

Broker settings live on the `accounts` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `broker_type` | TEXT | `'paper'` | `'paper'`, `'interactive_brokers'`, or `'interactive_brokers_web'` |
| `broker_host` | TEXT | NULL | TWS/Gateway host (IB only) |
| `broker_port` | INTEGER | NULL | TWS/Gateway port (IB only) |
| `broker_client_id` | INTEGER | NULL | IB client ID (IB only) |
| `live_trading_enabled` | INTEGER | `0` | **Safety gate** — see below |

---

## Live trading safety guard

`live_trading_enabled` is a hard gate that prevents real orders from being
sent accidentally.  It defaults to `0` and must be set to `1` manually.

**How to enable live trading for an account:**

```sql
-- Run directly against the DB. Never do this through a bot or script.
UPDATE accounts SET live_trading_enabled = 1 WHERE name = 'my-live-account';
```

**What happens without it:**

```python
# factory.py raises this — it will never be silenced automatically
LiveTradingNotEnabledError: Account 'my-account' has live_trading_enabled = 0.
Set live_trading_enabled = 1 on the account row to allow live orders.
This must be done manually — bots must never set this flag.
```

**Bot rules (enforced in `BOT_ARCHITECTURE_CONVENTIONS.md`):**

- Bots must never set `live_trading_enabled = 1`
- Bots must never catch or suppress `LiveTradingNotEnabledError`
- Test fixtures must always keep `live_trading_enabled = 0`

---

## IB connection defaults

| Environment | Port |
|-------------|------|
| TWS paper trading | 7497 |
| TWS live trading | 7496 |
| IB Gateway paper | 4002 |
| IB Gateway live | 4001 |

TWS/Gateway setup:
1. Open TWS or IB Gateway
2. Edit → Global Config → API → Settings
3. Enable "Enable ActiveX and Socket Clients"
4. Set the trusted IP (127.0.0.1 for local)

---

## IBKR Web API configuration

The Web API adapter is selected when `broker_type = 'interactive_brokers_web'`.
Unlike the socket/TWS adapter, it does **not** store live account identifiers or
session headers on the account row.

Primary IBKR Web API docs:

- Client Portal / Web API overview and endpoint guide:
  `https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/`
- IBKR Campus Web API landing page:
  `https://ibkrcampus.com/campus/ibkr-api-page/webapi-doc/`

Sensitive values are loaded from env vars or an ignored local config file:

- `TRADING_IBKR_WEB_API_ACCOUNT_ID`
- `TRADING_IBKR_WEB_API_BASE_URL` (defaults to `https://localhost:5000/v1/api`)
- `TRADING_IBKR_WEB_API_SESSION_TOKEN`
- `TRADING_IBKR_WEB_API_HEADERS_JSON`
- `TRADING_IBKR_WEB_API_VERIFY_SSL`
- `TRADING_IBKR_WEB_API_TIMEOUT_SECONDS`
- `TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED`
- `TRADING_IBKR_WEB_API_KEEPALIVE_INTERVAL_SECONDS`
- `TRADING_IBKR_WEB_API_CONFIG`

Recommended private setup for this repo:

- Keep real account IDs, names, cookies, and tokens in env vars or in a private
  config file **outside the repository**.
- Do not add them to account rows, tracked JSON fixtures, or shared docs.
- Create the file **outside the repo** and point
  `TRADING_IBKR_WEB_API_CONFIG` at it yourself with the required keys shown below.

Env-to-local-JSON mapping:

| Environment variable | Local JSON key | Notes |
|---|---|---|
| `TRADING_IBKR_WEB_API_ACCOUNT_ID` | `account_id` | Required account identifier |
| `TRADING_IBKR_WEB_API_BASE_URL` | `base_url` | Optional base URL override; repo default is local gateway |
| `TRADING_IBKR_WEB_API_SESSION_TOKEN` | `session_token` | Converted to `Cookie: api=...` if `headers` does not already provide `Cookie` |
| `TRADING_IBKR_WEB_API_HEADERS_JSON` | `headers` | Env form is a JSON-encoded object; file form is a plain JSON object |
| `TRADING_IBKR_WEB_API_VERIFY_SSL` | `verify_ssl` | Boolean; local gateway usually wants `false` unless you installed a trusted local cert |
| `TRADING_IBKR_WEB_API_TIMEOUT_SECONDS` | `timeout_seconds` | Positive number |
| `TRADING_IBKR_WEB_API_KEEPALIVE_ENABLED` | `keepalive_enabled` | Boolean; enables background `/tickle` keepalive while connected |
| `TRADING_IBKR_WEB_API_KEEPALIVE_INTERVAL_SECONDS` | `keepalive_interval_seconds` | Positive number; docs recommend about 60 seconds |
| `TRADING_IBKR_WEB_API_CONFIG` | — | Points to the config file path itself; not a key inside the file |

Recommended external config workflow:

1. Create a private directory outside the repository, for example:
   - Linux: `~/.config/trading_strategies/`
   - macOS: `~/.config/trading_strategies/`
2. Create `ibkr_web_api_config.json` in that directory.
3. Restrict permissions so only your user can read it:

```bash
mkdir -p ~/.config/trading_strategies
chmod 700 ~/.config/trading_strategies
touch ~/.config/trading_strategies/ibkr_web_api_config.json
chmod 600 ~/.config/trading_strategies/ibkr_web_api_config.json
```

4. Put your private IBKR values in that file.
5. Export `TRADING_IBKR_WEB_API_CONFIG` to point at the external path before
   running trading code:

```bash
export TRADING_IBKR_WEB_API_CONFIG="$HOME/.config/trading_strategies/ibkr_web_api_config.json"
```

Recommended external file contents:

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

Current Web API method coverage:

- Session validation via `/iserver/auth/status`, `/portfolio/accounts`, and `/iserver/accounts`
- Account values via `/portfolio/{accountId}/ledger` and `/portfolio/{accountId}/summary`
- Position reads via `/portfolio/{accountId}/positions/0`
- Quote snapshots via `/iserver/marketdata/snapshot`
- Orders via `/iserver/account/{accountId}/orders`, `/iserver/reply/{messageId}`, and `/iserver/account/{accountId}/order/{orderId}`
- Open-order reconciliation via `/iserver/account/orders`

Documented Client Portal pacing limits from
`https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/`:

- Global limit: **10 total requests per second**
- `GET /fyi/unreadnumber`: **1 request per second**
- `GET /fyi/settings`: **1 request per second**
- `POST /fyi/settings/{typecode}`: **1 request per second**
- `GET /fyi/disclaimer/{typecode}`: **1 request per second**
- `PUT /fyi/disclaimer/{typecode}`: **1 request per second**
- `GET /fyi/deliveryoptions`: **1 request per second**
- `PUT /fyi/deliveryoptions/email`: **1 request per second**
- `POST /fyi/deliveryoptions/device`: **1 request per second**
- `DELETE /fyi/deliveryoptions/{deviceId}`: **1 request per second**
- `GET /fyi/notifications`: **1 request per second**
- `GET /fyi/notifications/more`: **1 request per second**
- `PUT /fyi/notifications/{notificationId}`: **1 request per second**
- `GET /iserver/account/orders`: **1 request per 5 seconds**
- `GET /iserver/account/pnl/partitioned`: **1 request per 5 seconds**
- `GET /iserver/account/trades`: **1 request per 5 seconds**
- `GET /iserver/marketdata/history`: **5 concurrent requests**
- `GET /iserver/marketdata/snapshot`: **10 requests per second**
- `GET /iserver/scanner/params`: **1 request per 15 minutes**
- `POST /iserver/scanner/run`: **1 request per second**
- `POST /pa/performance`: **1 request per 15 minutes**
- `POST /pa/summary`: **1 request per 15 minutes**
- `POST /pa/transactions`: **1 request per 15 minutes**
- `GET /portfolio/accounts`: **1 request per 5 seconds**
- `GET /portfolio/subaccounts`: **1 request per 5 seconds**
- `GET /sso/validate`: **1 request per minute**
- `GET /tickle`: **1 request per second**

Other operational notes from the docs worth preserving:

- A session can remain authenticated for up to 24 hours, but resets at midnight
  for the relevant IBKR region.
- Sessions time out after about 6 minutes without requests; `/tickle` should be
  called regularly to keep the session alive.
- IBKR recommends calling `/tickle` about once per minute for keepalive.
- This repo's Web API client can run a background keepalive thread while
  connected; it is enabled by default with a 60-second interval.
- `GET /iserver/auth/status` is the primary endpoint for checking brokerage
  session state.
- Client Portal Gateway defaults to localhost port `5000`, but the port is
  configurable in `conf.yaml`.

---

## Switching IB backends

The `InteractiveBrokersAdapter` is backend-agnostic.  Change one variable in
`factory.py` to switch:

```python
# trading/brokers/factory.py
IB_CLIENT_BACKEND: str = "ib_async"   # default — uses ib_async library
IB_CLIENT_BACKEND: str = "ibapi"      # uses IBKR native ibapi (implement IbApiClient first)
```

**`ib_async` (default):**  Community-maintained fork of `ib_insync`
([ib-api-reloaded/ib_async](https://github.com/ib-api-reloaded/ib_async)).
Near-identical API to `ib_insync`, actively maintained.  Install: `pip install ib_async`.

**`ibapi` (stub):**  IBKR's official Python API.  Callback-based architecture
(EWrapper + EClient).  Implement `IbApiClient` in `trading/brokers/ib_client.py`
following the skeleton in its docstring.  Install: `pip install ibapi`.

---

## Async fill reconciliation

IB is asynchronous — `place_order` returns `status = SUBMITTED`, not `FILLED`.
Fills arrive later via IB callbacks.

The runtime service handles this in two parts:

1. **`_record_runtime_trade`** — persists the SUBMITTED `broker_order` row immediately.
   The trade is NOT recorded in the ledger yet.

2. **`reconcile_open_ib_orders`** — polls IB for fill updates on all open orders.
   When an order transitions to FILLED:
   - Updates the `broker_orders` row
   - Inserts `order_fills` rows
   - Calls `record_trade` to add the fill to the account ledger

Call `reconcile_open_ib_orders` periodically in your trading loop:

```python
from trading.services.auto_trader_runtime_service import reconcile_open_ib_orders

newly_filled = reconcile_open_ib_orders(conn, account_name, account, fee=0.005)
```

---

## Adding a new broker

1. Create `trading/brokers/<name>_adapter.py` implementing `BrokerConnection`
2. Add a `_BROKER_TYPE_<NAME>` constant and routing branch in `factory.py`
3. Add the `broker_type` value to the `accounts.broker_type` `CHECK` constraint
   (or document the allowed values if no DB-level constraint exists)
4. Add tests in `tests/trading/test_brokers.py`
5. Update this document
