# Trading Module Boundaries (Draft)

Purpose: clarify ownership and dependency direction so the trading app is easier to extend safely.

Related plan: `docs/architecture/trading-structure-migration-plan.md`

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
2. Moved auto-trader optimal-strategy history query behind `fetch_strategy_backtest_returns(...)`.
3. Split CLI parser assembly into grouped modules in `trading/interfaces/cli/commands/`.
4. Converted `trading.models` from a single file to a package (`trading/models/`).
5. Extracted paper trading command handlers into grouped modules under `trading/interfaces/cli/handlers/` with explicit dependency wiring.
6. Added backtesting config/result dataclasses in `trading/models/backtesting.py`.
7. Split command dispatch implementation into grouped modules under `trading/interfaces/cli/handlers/`.
8. Extracted account persistence SQL into `trading/repositories/accounts_repository.py` and rewired `trading/accounts.py` as a domain/service facade.
9. Extracted snapshot persistence SQL into `trading/repositories/snapshots_repository.py` and rewired `trading/reporting.py` to consume repository adapters.
10. Extracted auto-trader orchestration into dedicated services consumed by `trading/auto_trader.py` wrappers for API/test compatibility.
11. Extracted auto-trader policy logic into `trading/domain/auto_trader_policy.py` and moved rotation state update SQL into `trading/repositories/rotation_repository.py`.
12. Split auto-trader services into `trading/services/rotation_service.py` and `trading/services/trade_execution_service.py`.
13. Extracted `run_backtest(...)` orchestration into `trading/backtesting/services/execution_service.py` and kept `trading/backtesting/backtest.py` as wrapper preserving existing monkeypatch seams.
14. Standardized backtesting service read APIs to `fetch_*` and removed legacy `load_*` aliases.
15. Migrated direct imports to concrete handler/service modules and removed import-only facades.

Planned next slices:

1. Continue extracting any future backtest-table reads in non-backtesting modules into `trading/backtesting/history.py`.
2. Consider moving additional shared reporting/output DTOs into `trading/models/`.
3. Continue replacing compatibility wrappers with direct imports once test monkeypatch seams are no longer required.

## Why Only One Model File Exists Today

- `trading/models.py` currently holds only `AccountState`, shared by accounting/reporting/auto-trader.
- Backtesting dataclasses are currently defined in `trading/backtesting/backtest.py`.
- This is functional, but less discoverable. A package-based model layout can make ownership clearer.

## Naming Conventions

To keep module intent obvious, use verb prefixes by layer:

- Repositories (`.../repositories/...`)
  - `fetch_*` for reads/queries.
  - `insert_*`, `update_*`, `delete_*` for writes.
  - Avoid domain words like `resolve_*` in repository functions.

- Services (`.../services/...`)
  - `fetch_*` when primarily orchestrating retrieval and shaping data.
  - `run_*` / `execute_*` for workflows with side effects.
  - `resolve_*` for derivation/normalization of inputs or config.

- Domain (`.../domain/...`)
  - Prefer descriptive pure-function names over transport/data-access verbs.
  - Keep dependencies on DB, network, and CLI I/O out of domain modules.

Compatibility rule:

- When renaming existing functions for consistency, keep legacy aliases in place only during explicit migration windows, then remove them after callers and tests are updated.

## Preferred Imports

Use direct imports from concrete grouped modules rather than import-only facades.

Preferred:

```python
from trading.interfaces.cli.commands import build_parser
from trading.interfaces.cli.handlers.router import dispatch_command
from trading.interfaces.cli.handlers.shared import common_account_config_kwargs, resolve_learning_enabled
from trading.services.rotation_service import select_optimal_strategy
from trading.services.trade_execution_service import run_for_account
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
```

Avoid:

```python
from trading.paper_trading_handlers import ...
from trading.services import auto_trader_service
from trading.backtesting.services.history_service import load_strategy_backtest_returns
```
