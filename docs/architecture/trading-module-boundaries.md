# Trading Module Boundaries (Draft)

Purpose: clarify ownership and dependency direction so the trading app is easier to extend safely.

## Current Domain Areas

- Account domain
  - Files: `trading/accounts.py`, `trading/accounting.py`, `trading/reporting.py`
  - Responsibility: account metadata, trade ledger accounting, account-level reporting.

- Execution domain
  - Files: `trading/auto_trader.py`, `trading/paper_trading.py`
  - Responsibility: orchestrating daily paper trades and command dispatch.

- Backtesting domain
  - Folder: `trading/backtesting/`
  - Responsibility: historical simulation, walk-forward runs, and backtest analytics.

- Infrastructure domain
  - Folder: `trading/database/`
  - Responsibility: SQLite schema/backends and DB admin/export helpers.

## Dependency Direction (Target)

Preferred direction:

1. Entry points and orchestrators may depend on domain services.
2. Domain services may depend on infrastructure adapters.
3. Domain modules should avoid reaching into another domain's private tables or SQL directly.

Concretely:

- `trading/auto_trader.py` should consume backtesting history through backtesting helpers, not inline SQL against `backtest_*` tables.
- Backtesting SQL and backtest-specific schema assumptions should stay inside `trading/backtesting/`.

## Low-Risk Refactor Slices

Completed in this iteration:

1. Introduced `trading/backtesting/history.py`.
2. Moved auto-trader optimal-strategy history query behind `load_strategy_backtest_returns(...)`.
3. Split CLI parser assembly into grouped modules in `trading/cli_commands/`.
4. Converted `trading.models` from a single file to a package (`trading/models/`).
5. Extracted paper trading command handlers into `trading/paper_trading_handlers.py` with explicit dependency wiring.
6. Added backtesting config/result dataclasses in `trading/models/backtesting.py`.

Planned next slices:

1. Continue extracting any future backtest-table reads in non-backtesting modules into `trading/backtesting/history.py`.
2. Evaluate splitting `trading/paper_trading_handlers.py` into account/report/backtest handler groups if it grows.
3. Consider moving additional shared reporting/output DTOs into `trading/models/`.

## Why Only One Model File Exists Today

- `trading/models.py` currently holds only `AccountState`, shared by accounting/reporting/auto-trader.
- Backtesting dataclasses are currently defined in `trading/backtesting/backtest.py`.
- This is functional, but less discoverable. A package-based model layout can make ownership clearer.
