# Infrastructure Map

Type: map
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-23
Purpose: Inventory the `src/infrastructure/` package — the concrete adapters and external-dependency boundaries that the trading domain depends on only through ports, plus the database backend and static config assets.
Related: [Trading Package Map](trading-package-map.md), [Architecture Conventions](../architecture/architecture-conventions.md), [Broker Integration](../reference/broker-integration.md)

## Purpose

`src/infrastructure/` is the sibling of `src/trading/` that isolates **external/concrete details** from the domain. Each subpackage owns a third-party SDK or I/O boundary; the trading layers depend on a port (a Protocol in `src/trading/`) and receive a concrete instance by injection.

## Boundary rules

- `src/infrastructure/` owns concrete adapters and third-party SDK imports. Trading code consumes
  ports and receives adapters at composition seams.
- `src/infrastructure/database/` is the one infrastructure package the domain reaches *through repositories*: only `src/trading/repositories/` (and the documented `accounts/runtime_loader.py` exception) import it.
- Import ownership is enforced by `python -m scripts.checks.repo.layer_check`.

## Module Directory

### `src/infrastructure/database/`

DB infrastructure. Imported only by `src/trading/repositories/` and the documented `runtime_loader.py` exception.

| Module | Responsibility |
|---|---|
| `backend.py` | DB connection/backend factory and backend selection |
| `config.py` | DB path and environment config (`get_db_path`) |
| `connection.py` | Runtime connection gate: `ensure_db()` verifies the Alembic revision (never migrates); `db_session()` |
| `schema_version.py` | Expected Alembic head constant + plain-SQL revision reader (runtime-safe, no Alembic import) |
| `migration_runner.py` | Programmatic Alembic runner (upgrade/downgrade, reference builds) over the active backend — ops-only |
| `alembic/env.py` | Repository-owned Alembic environment (connection-mode only) |
| `alembic/versions/` | Immutable numeric migration revisions (`0001_current_schema`, …) — the schema source of truth |

### `src/infrastructure/brokers/`

Broker connection adapters and routing. The factory is the sole `broker_type` routing point and owns the `live_trading_enabled` guard. Service/domain layers depend only on `BrokerConnection` from `src/trading/domain/broker_connection.py`.

| Module | Responsibility |
|---|---|
| `factory.py` | `broker_type` → `BrokerConnection` routing; `live_trading_enabled` safety guard |
| `paper_adapter.py` | Simulated immediate-fill paper broker (default) |
| `ibkr_web/adapter.py` | Interactive Brokers Client Portal / Web API `BrokerConnection` adapter |
| `ibkr_web/client.py` | IBKR Web API HTTP client: session validation/keepalive, account and market-data queries, contract lookup, and order operations |
| `ibkr_web/pacing.py` | Process-wide IBKR Web API global and endpoint-specific request pacing guard |
| `ibkr_web/settings.py` | Operator-managed IBKR Web API settings loaded from environment variables or ignored local configuration |

### `src/infrastructure/brokers/ibkr_socket/`

TWS/IB Gateway socket support with interchangeable `ib_async` and native `ibapi` clients.

| Module | Responsibility |
|---|---|
| `adapter.py` | Backend-neutral socket `BrokerConnection` adapter |
| `contracts.py` | Project-owned normalized socket client records |
| `protocol.py` | Backend-neutral socket client protocol |
| `ib_async_client.py` | Working `ib_async` socket client |
| `ibapi_client.py` | Native `ibapi` connection, order, position, account-summary, and snapshot-quote callbacks |
| `factory.py` | Socket backend selection and broker construction |

### `src/infrastructure/feature_providers/`

External-data feature providers for alternative strategies. Each subclasses
`ExternalFeatureProvider` (contract in `src/trading/domain/feature_provider.py`) and degrades
gracefully to `available=False`.

| Module | Responsibility |
|---|---|
| `news_provider.py` | `NewsFeatureProvider` — news sentiment features |
| `policy_provider.py` | `PolicyFeatureProvider` — policy/macro features |
| `social_provider.py` | `SocialFeatureProvider` — social/Reddit sentiment features |

### `src/infrastructure/market_data/`

Concrete market-data adapter + provider factory. The `MarketDataProvider` port and the proxy
feature provider stay in `src/trading/services/market_data/`.

| Module | Responsibility |
|---|---|
| `demo_provider.py` | Deterministic offline `DemoMarketDataProvider` |
| `yfinance_provider.py` | Network-backed `YFinanceProvider` and yfinance SDK boundary; guards live fetches with a `common.rate_limit.RateLimiter` (only cache-miss network calls) |
| `factory.py` | `build_provider` + provider routing (`TRADING_MARKET_DATA_PROVIDER`, else the `yfinance` default); an unsupported name raises at build time |
| `cache.py` | Transport-level market-data cache (pickle-to-disk with TTL), used only by the adapter |

**Operational env knobs** (all optional; sensible defaults):

| Env var | Effect |
|---|---|
| `TRADING_MARKET_DATA_CACHE_DIR` | Override the on-disk cache directory (default `local/cache/market_data/`) |
| `TRADING_MARKET_DATA_CACHE_DISABLED` | Truthy disables the 24h disk cache (forces every fetch to hit the provider) |
| `TRADING_YF_MAX_CALLS` | Per-run cumulative ceiling on live Yahoo requests before `RateLimitExceeded` (default `1000`; `0` disables). The deterministic runaway-loop backstop |
| `TRADING_YF_MIN_INTERVAL_SECONDS` | Minimum spacing between live Yahoo requests (default `0` = off). Set e.g. `0.5` to pace a large cold research sweep |

The guard counts only real network fetches — cache hits neither pace nor count — so a
multi-strategy sweep on one account/universe/date-window stays far under the ceiling.

### `src/infrastructure/config/`

Static file-backed configuration assets. Read at runtime; not imported as Python modules (except by `src/trading/services/profiles/`).

| Asset | Description |
|---|---|
| `account_profiles/` | JSON account profile presets |
| `trade_universes/` | Trade-universe definition files |
| `account_trade_caps.json` | Account-level trade-cap limits |
| `trade_universe.txt` | Default trade-universe ticker list |
| `trade_universe_sp500_broad.txt` | Broad S&P 500 trade universe |

## Related References

- [trading-package-map.md](trading-package-map.md) — the `src/trading/` package this infrastructure serves
- `docs/architecture/architecture-conventions.md` — authoritative ownership map and boundary rules
- [broker-integration.md](../reference/broker-integration.md) — broker abstraction, IB connection setup, live-trading safety
