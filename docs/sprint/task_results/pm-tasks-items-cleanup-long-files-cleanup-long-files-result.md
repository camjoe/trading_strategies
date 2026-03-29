# Result: Cleanup Long Files (Step 1 Research)

## Summary
Completed research for task `pm-tasks-items-cleanup-long-files` in `single` mode with `research` intent.

Focus areas reviewed:
1. Reducing long import sections.
2. Reducing parameter/value plumbing with classes/models.

Most actionable findings:
- The largest complexity driver is not import count, but parameter-heavy orchestration signatures.
- `trading/backtesting/services/execution_service.py` is the highest-value target because `run_backtest(...)` takes many injected callables.
- `paper_trading_ui/backend/schemas.py` has repeated request fields that can be safely consolidated via a shared base model.
- `paper_trading_ui/backend/routes/admin.py` has large keyword mapping from payload to service call, suitable for structured mapping helpers.

## Files Changed
- `docs/sprint/task_prompts/pm-tasks-items-cleanup-long-files-cleanup-long-files.md` (created earlier in this run sequence)
- `docs/sprint/task_results/pm-tasks-items-cleanup-long-files-cleanup-long-files-result.md` (this file)

No production code files were changed in this research step.

## Candidate Files (Prioritized)
1. `trading/backtesting/services/execution_service.py`
   - Reason: function signature has high callback dependency density.
2. `trading/services/auto_trader_runtime_service.py`
   - Reason: orchestration wrappers repeatedly pass dependency functions.
3. `paper_trading_ui/backend/schemas.py`
   - Reason: duplicated backtest request fields across multiple request models.
4. `paper_trading_ui/backend/routes/admin.py`
   - Reason: very large payload-to-service keyword mapping block.
5. `trading/backtesting/backtest.py`
   - Reason: broad import region and mixed concerns at module top.
6. `trading/accounts.py`
   - Reason: multi-symbol imports and repeated repo/coercion use patterns.
7. `paper_trading_ui/backend/services/accounts.py`
   - Reason: service/repository composition can be clearer with grouped dependencies.
8. `paper_trading_ui/backend/services/__init__.py`
   - Reason: public export surface should stay explicit and minimal.

## Import Shortening Research Findings
- Keep explicit imports as the default. This aligns with architecture guidance in `docs/architecture/trading-module-boundaries.md` (Import Rules: prefer direct imports; avoid import-only facades unless declared public entrypoint).
- Reduce top-of-file visual noise by:
  - Grouping imports by stdlib / third-party / local modules.
  - Sorting and collapsing multiline lists where still readable.
  - Extracting repeated typed aliases or dependency groups into local typed structures (not wildcard imports).
- Avoid `from module import *` and broad facade-only imports for trading modules.

## Encapsulation Research Findings
- Best Step 2 candidate: replace callable-heavy parameter lists with structured dependency bundles (`@dataclass` + Protocol/typed callables where helpful) in backtesting/runtime orchestration.
- For request models, create shared base schemas for overlapping fields (`BacktestRunRequest`, `WalkForwardRunRequest`, `BacktestPreflightRequest`) while preserving API field names.
- For route payload expansion, introduce a small mapping/helper object to keep API route code concise while preserving service boundaries.

## Step 2 Proposal
### Should Do
1. Introduce a dependency bundle type for `run_backtest(...)` in `trading/backtesting/services/execution_service.py`.
2. Extract shared base request model in `paper_trading_ui/backend/schemas.py` for duplicated backtest fields.
3. Refactor `paper_trading_ui/backend/routes/admin.py` payload mapping into a helper function/object to reduce route verbosity.

### Could Do
1. Normalize import grouping/order in `trading/backtesting/backtest.py` and `trading/accounts.py`.
2. Tighten public exports in `paper_trading_ui/backend/services/__init__.py` while keeping explicit, documented entrypoints.
3. Reduce wrapper churn in `trading/services/auto_trader_runtime_service.py` with a small orchestration context object.

## Rationale
These recommendations preserve existing behavior and align with current architecture boundaries:
- Interfaces orchestrate through services.
- Domain logic remains side-effect free.
- Import patterns stay explicit for maintainability and discoverability.

## Test / Audit Results
Commands run in this research step:

```powershell
$files = @(
  'trading/backtesting/services/execution_service.py',
  'trading/backtesting/backtest.py',
  'trading/services/auto_trader_runtime_service.py',
  'paper_trading_ui/backend/services/__init__.py',
  'paper_trading_ui/backend/routes/admin.py',
  'trading/accounts.py',
  'paper_trading_ui/backend/services/accounts.py',
  'trading/services/auto_trader_service.py'
)
foreach ($f in $files) {
  if (Test-Path $f) {
    $count = (Get-Content $f | Select-String -Pattern '^(from |import )').Count
    Write-Output ($f + ' :: import_lines=' + $count)
  }
}
```

Observed output:
- `trading/backtesting/services/execution_service.py :: import_lines=6`
- `trading/backtesting/backtest.py :: import_lines=23`
- `trading/services/auto_trader_runtime_service.py :: import_lines=13`
- `paper_trading_ui/backend/services/__init__.py :: import_lines=7`
- `paper_trading_ui/backend/routes/admin.py :: import_lines=7`
- `trading/accounts.py :: import_lines=7`
- `paper_trading_ui/backend/services/accounts.py :: import_lines=9`
- `trading/services/auto_trader_service.py :: import_lines=5`

Notes:
- Full test suite was not run because this was a research-only step with no production code changes and no commit/PR.
- Prior terminal context showed backend tests passing (`python -m pytest tests/paper_trading_ui/backend -q`).

## Risks
- Over-abstracting dependency bundles can reduce readability if done too broadly.
- Shared schema inheritance can become rigid if feature-specific fields diverge heavily.
- Import cleanup that reduces explicitness can conflict with architecture rules if it introduces facades/wildcards.

## PR Link
- N/A (research task; no branch/commit/PR created)

## Blockers / Notes
- Referenced path `local/prompt_start.md` was not present in workspace at execution time, so execution proceeded from `local/prompt_run.md` and task prompt artifacts directly.

## Step 2 Implementation Update
Implemented two `Should Do` items from the Step 2 proposal while preserving behavior:

1. Added structured dependency bundling for backtest execution.
   - File: `trading/backtesting/services/execution_service.py`
   - Change: Introduced `BacktestExecutionDependencies` dataclass and added a `deps` entrypoint to `run_backtest(...)`.
   - Compatibility: Kept the previous keyword-injection interface as a fallback to avoid breaking existing tests and call sites.

2. Updated backtest orchestration to use the new dependency bundle.
   - File: `trading/backtesting/backtest.py`
   - Change: Constructs `BacktestExecutionDependencies` once and passes it to `run_backtest_impl(...)`.

3. Extracted shared base request schema for backtest API payloads.
   - File: `paper_trading_ui/backend/schemas.py`
   - Change: Added `BacktestBaseRequest` and migrated:
     - `BacktestRunRequest`
     - `WalkForwardRunRequest`
     - `BacktestPreflightRequest`
   - Compatibility: Preserved field names and defaults used by existing backend service mappers.

## Step 2 Validation Results
Commands run:

```powershell
C:/Users/camer/Documents/Workspaces/camjoe/trading_strategies/.venv/Scripts/python.exe -m pytest tests/trading/backtesting/services/test_execution_service.py -q
```

Observed outcome:
- Functional tests passed, but command exited non-zero due to repository-wide coverage fail-under policy when running a narrow subset.

```powershell
C:/Users/camer/Documents/Workspaces/camjoe/trading_strategies/.venv/Scripts/python.exe -m pytest -q -o addopts= tests/trading/backtesting/services/test_execution_service.py tests/paper_trading_ui/backend/services/test_services_backtests.py
```

Observed outcome:
- `5 passed in 0.74s`

```powershell
C:/Users/camer/Documents/Workspaces/camjoe/trading_strategies/.venv/Scripts/python.exe -m pytest -q -o addopts= tests/trading/backtesting/test_backtest.py
```

Observed outcome:
- `23 passed in 1.55s`

Editor diagnostics:
- No errors in:
  - `trading/backtesting/services/execution_service.py`
  - `trading/backtesting/backtest.py`
  - `paper_trading_ui/backend/schemas.py`

## Remaining Should Do
- Refactor `paper_trading_ui/backend/routes/admin.py` payload mapping into a helper function/object to reduce route verbosity.

## PR Link
- N/A (implementation completed locally; no branch/commit/PR created in this run)
