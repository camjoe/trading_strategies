# Trading Structure Migration Plan (No-Break)

Purpose: define a target package hierarchy and a safe move order that keeps runtime behavior stable while improving discoverability and responsibility boundaries.

## Target Tree

```text
trading/
  application/
    services/
      ... (existing orchestration services)
  domain/
    ... (existing pure policy/math modules)
  infrastructure/
    repositories/
      ... (existing repositories)
    database/
      ... (existing database backends/admin)
  interfaces/
    cli/
      commands/
        ... (from cli_commands)
      handlers/
        ... (from handlers)
      entrypoints/
        paper_trading.py (or wrapper)
    runtime/
      jobs/
        ... (from trading/scripts)
      config/
        account_trade_caps.json
  features/
    backtesting/
      ... (existing trading/backtesting package)
    accounts/
      ... (future package split from flat modules)
    execution/
      ... (future package split from auto_trader/paper_trading flows)
  config/
    account_profiles/
      aggressive.json
      conservative.json
      default.json
  models/
    ... (existing typed DTO package)
```

## Design Rules

1. Keep domain and application layers independent of CLI/runtime adapter code.
2. Keep all file-backed static configuration under `trading/config/`.
3. Keep operational scripts and schedulers under one runtime adapter namespace.
4. Move into `trading/features/` only when at least two feature packages are ready.

## No-Break Migration Sequence

### Slice 0 (Completed)

- Centralize account profile preset path resolution in one module.
- Relocate preset assets from `trading/account_profiles/` to `trading/config/account_profiles/`.
- Keep legacy path fallback for CLI compatibility.

### Slice 1 (Completed)

- Introduce `trading/interfaces/cli/` package.
- Move `trading/cli_commands/` to `trading/interfaces/cli/commands/`.
- Move `trading/handlers/` to `trading/interfaces/cli/handlers/`.
- Update internal imports, tests, and docs to canonical CLI interface paths.
- Remove temporary wrapper modules once repo usages reach zero.

### Slice 2 (Completed)

- Introduce `trading/interfaces/runtime/` package.
- Move `trading/scripts/` to `trading/interfaces/runtime/jobs/`.
- Move `account_trade_caps.json` to `trading/interfaces/runtime/config/`.
- Update scheduler and docs references to canonical runtime job paths.

### Slice 3

- Create `trading/features/` package.
- Move `trading/backtesting/` to `trading/features/backtesting/`.
- Keep `trading/backtesting/__init__.py` compatibility wrapper importing from new location.
- Update docs and preferred import guidance to feature path.

### Slice 4

- Package flat account/execution modules as feature packages (`features/accounts`, `features/execution`).
- Retain stable public module wrappers until all callers/tests/docs are migrated.

### Slice 5

- Remove any remaining wrappers after two green CI cycles and zero repo usages from `rg` checks.

## Compatibility Shim Rules

1. Wrapper modules should re-export only public symbols, not private helpers.
2. Wrapper modules should include a short deprecation note and planned removal milestone.
3. Wrapper removal is allowed only after:
   - `pytest` and smoke are green,
   - no internal imports point at wrapper path,
   - docs updated to canonical paths.

## Validation Checklist Per Slice

1. `python -m pytest -o addopts="" tests/trading`
2. `python -m mypy paper_trading_ui/backend trading --python-version 3.12 --ignore-missing-imports --follow-imports=skip`
3. `python -m scripts.check_docs_freshness.py --repo-root .`
4. `python -m scripts.ci_smoke --skip-frontend` (for fast preflight)

## Rollback Strategy

- If a slice fails, keep wrapper shims and revert only moved import targets while preserving new package directories.
- Do not delete old paths until tests and docs are green for the new canonical paths.
