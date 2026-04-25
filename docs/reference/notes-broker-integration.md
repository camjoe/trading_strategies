# Broker Integration Notes

## Overview

The broker layer provides a uniform interface over paper and live broker connections.
All order submission, fill tracking, and account data flows through this abstraction —
the rest of the trading engine never touches a broker SDK directly.

**Current/default IBKR path:** `interactive_brokers_web` via the Client Portal /
Web API.

**Legacy alternative retained in-repo:** `interactive_brokers` via the older
socket/TWS flow.

---

## Architecture

```
auto_trading/runtime
        │
        ▼
trading/brokers/factory.py          ← resolves BrokerConnection for an account
        │
        ├── PaperBrokerAdapter       ← default; immediate fills, zero commission
        │
        ├── InteractiveBrokersAdapter        ← legacy socket/TWS path
                │
                └── IBClientProtocol (injected)
                        ├── IbAsyncClient   ← wraps ib_async (legacy support)
                        └── IbApiClient     ← wraps IBKR native ibapi (legacy stub)
        │
        └── InteractiveBrokersWebAdapter    ← current/default local gateway path
                │
                └── InteractiveBrokersWebClient
                        └── IBKR Client Portal / Campus Web API
```

### Key files

| File | Purpose |
|------|---------|
| `trading/brokers/base.py` | `BrokerConnection` ABC, `BrokerOrder`, `OrderFill`, `OrderStatus` |
| `trading/brokers/paper_adapter.py` | Simulated immediate-fill paper broker |
| `trading/brokers/legacy/ib_adapter.py` | Legacy Interactive Brokers socket/TWS live adapter |
| `trading/brokers/legacy/ib_client.py` | Legacy socket/TWS client abstraction (`IBClientProtocol`, `IbAsyncClient`, `IbApiClient` stub) |
| `trading/brokers/ib_web_adapter.py` | Interactive Brokers Web API live adapter |
| `trading/brokers/ib_web_client.py` | Web API config loader + HTTP client |
| `trading/brokers/factory.py` | Routes accounts → correct `BrokerConnection` |
| `trading/repositories/broker_orders.py` | DB persistence for orders and fills |
| `trading/services/auto_trading/runtime.py` | Wires broker into trade execution loop |

---

## Account configuration

Broker settings live on the `accounts` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `account_kind` | TEXT | `'managed'` | Account role / visibility: `'managed'`, `'local'`, or `'test_shadow'` |
| `broker_type` | TEXT | `'paper'` | `'paper'`, `'interactive_brokers'` (legacy), or `'interactive_brokers_web'` |
| `broker_host` | TEXT | NULL | TWS/Gateway host for the legacy socket/TWS path |
| `broker_port` | INTEGER | NULL | TWS/Gateway port for the legacy socket/TWS path |
| `broker_client_id` | INTEGER | NULL | IB client ID for the legacy socket/TWS path |
| `live_trading_enabled` | INTEGER | `0` | **Safety gate** — see below |

---

## `account_kind` vs `broker_type`

These two fields answer different questions:

- `account_kind` says **what role the account plays in this repo**.
  - `managed`: normal paper-trading UI account managed through the app.
  - `local`: locally created strategy-testing account that should still remain visible in normal account lists.
  - `test_shadow`: internal backing row for the virtual `test_account`; hidden from normal account lists.
- `broker_type` says **which execution backend the account uses**.
  - Today that is `paper`, `interactive_brokers` (legacy), or `interactive_brokers_web`.
  - If an Alpaca integration is added later, Alpaca would become a new `broker_type`, not a new `account_kind`.

In other words: IBKR vs Alpaca is a broker concern; managed vs local vs test-shadow is an account-role concern.

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

## Legacy socket/TWS connection defaults

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

The Web API adapter is the current/default IBKR path and is selected when
`broker_type = 'interactive_brokers_web'`.
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

Read-only smoke test command:

```bash
python -m scripts.ibkr_web_api_smoke_test
```

Optional paper-order lifecycle check:

```bash
python -m scripts.ibkr_web_api_smoke_test \
  --paper-order-check \
  --paper-order-symbol AAPL \
  --paper-order-limit-price 1.00
```

What it does:

- Loads private config via the existing Web API settings loader.
- Validates the authenticated brokerage session and configured account visibility.
- Fetches ledger, summary, and positions through the existing client.
- Prints sanitized pass/fail output only; it does not place orders.
- When explicitly requested, it can also place a small paper-only limit order,
  check order status, poll live orders, inspect recent trades, and request
  cancellation by order id when the lifecycle state is still cancellable.

Recommended workflow:

1. Start the local Client Portal Gateway.
2. Authenticate it in the browser.
3. Export `TRADING_IBKR_WEB_API_CONFIG` to your external config path.
4. Run `python -m scripts.ibkr_web_api_smoke_test`.
5. If you share results back here, redact anything beyond the script's summary output.

Paper-order check notes:

- Use a **paper account only**.
- Use a clearly non-marketable limit price so the test order stays cancellable.
- The optional order check is gated behind `--paper-order-check`; the default
  smoke test remains read-only.
- Outside market hours, IBKR may leave the order in `PreSubmitted`; that still
  proves the submit path worked even if no fill occurs.

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
- The auto-trader runtime now reuses one broker connection per account trade
  loop, so IBKR Web API keepalive remains active across multi-trade account runs
  instead of reconnecting around every individual order.
- `GET /iserver/auth/status` is the primary endpoint for checking brokerage
  session state.
- Client Portal Gateway defaults to localhost port `5000`, but the port is
  configurable in `conf.yaml`.

---

## Switching IB backends

The `InteractiveBrokersAdapter` is backend-agnostic. Change one variable in
`trading/brokers/legacy/factory.py` to switch:

```python
# trading/brokers/legacy/factory.py
IB_CLIENT_BACKEND: str = "ib_async"   # default — uses ib_async library
IB_CLIENT_BACKEND: str = "ibapi"      # uses IBKR native ibapi (implement IbApiClient first)
```

**`ib_async` (default):**  Community-maintained fork of `ib_insync`
([ib-api-reloaded/ib_async](https://github.com/ib-api-reloaded/ib_async)).
Near-identical API to `ib_insync`, actively maintained.  Install: `pip install ib_async`.

**`ibapi` (stub):**  IBKR's official Python API.  Callback-based architecture
(EWrapper + EClient).  Implement `IbApiClient` in `trading/brokers/legacy/ib_client.py`
following the skeleton in its docstring.  Install: `pip install ibapi`.

---

## Async fill reconciliation

IB is asynchronous — `place_order` returns `status = SUBMITTED`, not `FILLED`.
Fills arrive later via IB callbacks.

The runtime service handles this in two parts:

1. **`_record_runtime_trade`** — persists the SUBMITTED `broker_order` row immediately.
   The trade is NOT recorded in the ledger yet.

2. **`reconcile_open_broker_orders`** — polls the active broker path for fill updates on all open orders.
   When an order transitions to FILLED:
   - Updates the `broker_orders` row
   - Inserts `order_fills` rows
   - Calls `record_trade` to add the fill to the account ledger

Call `reconcile_open_broker_orders` periodically in your trading loop:

```python
from trading.services.auto_trading.runtime import reconcile_open_broker_orders

newly_filled = reconcile_open_broker_orders(conn, account_name, account, fee=0.005)
```

---

## Adding a new broker

1. Create `trading/brokers/<name>_adapter.py` implementing `BrokerConnection`
2. Add a `_BROKER_TYPE_<NAME>` constant and routing branch in `factory.py`
3. Add the `broker_type` value to the `accounts.broker_type` `CHECK` constraint
   (or document the allowed values if no DB-level constraint exists)
4. Add tests in `tests/trading/brokers/` (for factory/adapter coverage)
5. Update this document
