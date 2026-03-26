# Common

Shared cross-package utilities used by trading and trends modules.

## Market Data Provider Switching

The market data layer supports provider selection via environment variables or config.

Resolution order:

1. TRADING_MARKET_DATA_PROVIDER
2. provider in local/market_data_config.json (or TRADING_MARKET_DATA_CONFIG)
3. default yfinance

Current implemented provider:

- yfinance

Planned provider names already reserved in config/runtime selection:

- yahooquery

Planned providers currently raise NotImplementedError with a clear message so you can wire config now without silently falling back.

Example config file:

- common/market_data_config.example.json
