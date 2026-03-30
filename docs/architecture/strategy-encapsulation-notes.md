# Strategy Encapsulation Notes

Purpose: save a clear snapshot of where strategy logic currently lives and provide reusable prompts for a future strategy-class refactor.

## Where Strategy Code Lives Today

Primary strategy signal ownership:

- `trading/backtesting/domain/strategy_signals.py`
  - `StrategySpec` dataclass (strategy metadata and function pointer).
  - `STRATEGY_REGISTRY` (all built-in strategy definitions).
  - `resolve_strategy(...)` and `resolve_signal(...)` (lookup and dispatch).

Main consumers of strategy behavior:

- `trading/backtesting/services/execution_service.py`
  - Resolves active strategy and strategy spec.
  - Computes buy/sell/hold signals for each ticker.
  - Loads feature bundles when a strategy requires feature columns.

- `trading/backtesting/backtest.py`
  - Wires strategy resolver and signal resolver into execution service.

- `trading/rotation.py`
  - Resolves currently active strategy for runtime account state.
  - Parses and advances strategy rotation schedules.

- `trading/services/rotation_service.py`
  - Selects optimal strategy from historical backtest returns.

- `trading/services/auto_trader_runtime_service.py`
  - Runtime composition for rotation and strategy-aware execution.

- `trading/domain/auto_trader_policy.py`
  - Uses strategy name text to bias side selection in `choose_side(...)`.

## Why A Strategy-Focused Class Helps

Current shape is already close to a strategy boundary, but logic is split between:

- registry lookup functions,
- signal dispatch functions,
- string-based strategy heuristics in policy code,
- and service-level wiring.

A dedicated class can:

- centralize strategy lookup, aliases, fallback rules, and signal execution,
- reduce function-parameter threading across service layers,
- make strategy metadata explicit (style, required features, risk profile),
- and reduce accidental behavior drift from string matching.

## Suggested Incremental Refactor Shape

1. Add a `StrategyRegistry` class in `trading/backtesting/domain/`.
2. Keep `StrategySpec` and existing strategy definitions unchanged at first.
3. Move `resolve_strategy(...)` and `resolve_signal(...)` behavior behind class methods.
4. Keep compatibility wrappers so current callers still work.
5. Migrate `execution_service.py` to consume the class directly.
6. Optionally migrate runtime policy heuristics to metadata instead of substring matching.

Guardrails:

- No business behavior changes.
- No public API contract changes in top-level facades.
- No data contract/schema changes.
- Keep tests green after each slice.

## Prompt Templates For Future Work

Use one of these prompts when resuming this effort.

### Prompt: Architecture Audit Only

```text
Audit strategy architecture boundaries for trading and backtesting.
Focus on strategy ownership, dependency direction, and call-site complexity.
Do not edit code.
Return:
1) current structure map,
2) top 5 structural issues,
3) low-risk refactor slices ranked by impact.
Reference docs/architecture/strategy-encapsulation-notes.md.
```

### Prompt: Safe First Refactor Slice

```text
Implement the first safe slice from docs/architecture/strategy-encapsulation-notes.md:
- add a StrategyRegistry class in backtesting domain,
- preserve behavior and public APIs,
- keep compatibility wrappers for existing resolve_strategy/resolve_signal calls,
- migrate only backtesting execution path to the class.

Validation required:
- run focused tests for trading/backtesting,
- report changed files and risk notes.
```

### Prompt: Runtime Policy Follow-Up

```text
Continue strategy encapsulation by removing string-substring strategy heuristics
from trading/domain/auto_trader_policy.py and replacing them with explicit strategy metadata.
Do not change business behavior.
Add or update tests for policy decisions.
Reference docs/architecture/strategy-encapsulation-notes.md.
```

### Prompt: Commit Message Help

```text
Summarize strategy encapsulation changes for commit.
Follow repository commit-message workflow and include README consistency findings.
Provide 3 short commit subject options in separate fenced blocks.
```

## Validation Commands To Reuse

```sh
python -m pytest tests/trading/backtesting -q -o addopts=
python -m pytest tests/trading/test_auto_trader.py tests/trading/test_trade_execution_service.py -q -o addopts=
python -m scripts.checks.readme_check --max-age-days 90
```
