# Infrastructure Map

Type: map
Status: Active
Created: 2026-06-24
Last Reviewed: 2026-07-02
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
| `init.py` | DB initialization (`ensure_db`) — applies schema + migrations |
| `migrations.py` | Hand-rolled schema migration runner (`ColumnMigration`, column guards) |
| `schema.py` | Table DDL definitions (source of truth for the schema) |
| `sql_helpers.py` | Low-level SQL utilities (`in_placeholders`, coercion helpers) |

### `src/infrastructure/brokers/`

Broker connection adapters and routing. The factory is the sole `broker_type` routing point and owns the `live_trading_enabled` guard. Service/domain layers depend only on `BrokerConnection` from `src/trading/domain/broker_connection.py`.

| Module | Responsibility |
|---|---|
| `factory.py` | `broker_type` → `BrokerConnection` routing; `live_trading_enabled` safety guard |
| `paper_adapter.py` | Simulated immediate-fill paper broker (default) |
| `ib_web_adapter.py` | Interactive Brokers Client Portal / Web API `BrokerConnection` adapter |
| `ib_web_client.py` | Low-level IBKR Web API HTTP client used by the web adapter |

### `src/infrastructure/brokers/legacy/`

Legacy TWS/socket broker support (ib_async / TWS), retained behind the same factory.

| Module | Responsibility |
|---|---|
| `factory.py` | Legacy TWS/socket broker construction |
| `ib_adapter.py` | Legacy ib_async/TWS `BrokerConnection` adapter |
| `ib_client.py` | Legacy TWS socket client |

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
| `providers.py` | Concrete `MarketDataProvider`s (`YFinanceProvider`, `UnavailableProvider` placeholders) |
| `factory.py` | `build_provider` + provider routing (env/config resolution) + `supported_provider_names` |
| `cache.py` | Transport-level market-data cache (pickle-to-disk with TTL), used only by the adapter |

### `src/infrastructure/config/`

Static file-backed configuration assets. Read at runtime; not imported as Python modules (except by `src/trading/services/profiles/`).

| Asset | Description |
|---|---|
| `account_profiles/` | JSON account profile presets |
| `trade_universes/` | Trade-universe definition files |
| `account_trade_caps.json` | Account-level trade-cap limits |
| `trade_universe.txt` | Default trade-universe ticker list |
| `trade_universe_sp500_broad.txt` | Broad S&P 500 trade universe |
| `market_data_config.example.json` | Example market-data provider config (copy to `local/` to override) |

## Related References

- [trading-package-map.md](trading-package-map.md) — the `src/trading/` package this infrastructure serves
- `docs/architecture/architecture-conventions.md` — authoritative ownership map and boundary rules
- [broker-integration.md](../reference/broker-integration.md) — broker abstraction, IB connection setup, live-trading safety
