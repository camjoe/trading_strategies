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
        └── InteractiveBrokersAdapter
                │
                └── IBClientProtocol (injected)
                        ├── IbAsyncClient   ← wraps ib_async (default, recommended)
                        └── IbApiClient     ← wraps IBKR native ibapi (stub)
```

### Key files

| File | Purpose |
|------|---------|
| `trading/brokers/base.py` | `BrokerConnection` ABC, `BrokerOrder`, `OrderFill`, `OrderStatus` |
| `trading/brokers/paper_adapter.py` | Simulated immediate-fill paper broker |
| `trading/brokers/ib_adapter.py` | Interactive Brokers live adapter |
| `trading/brokers/ib_client.py` | `IBClientProtocol` + `IbAsyncClient` + `IbApiClient` stub |
| `trading/brokers/factory.py` | Routes accounts → correct `BrokerConnection` |
| `trading/repositories/broker_orders_repository.py` | DB persistence for orders and fills |
| `trading/services/auto_trader_runtime_service.py` | Wires broker into trade execution loop |

---

## Account configuration

Broker settings live on the `accounts` table:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `broker_type` | TEXT | `'paper'` | `'paper'` or `'interactive_brokers'` |
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
