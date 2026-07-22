# ADR: Centralize UI Domain-Exception → HTTP Mapping

Type: adr
Status: Accepted
Created: 2026-06-27
Last Reviewed: 2026-07-14
Purpose: Decide how the FastAPI backend should map domain/validation errors to HTTP responses, replacing the per-route try/except → HTTPException duplication.
Related: [Architecture Conventions](../architecture/architecture-conventions.md) (UI Backend Boundary Rule + Cross-Cutting Patterns), [ADR 006](006-cross-cutting-decorators.md)

## Context

The FastAPI backend repeats a domain-error → `HTTPException` mapping across ~8
route/service files. The dominant shape is:

```python
try:
    result = some_service(conn, ...)
except ValueError as error:
    raise HTTPException(status_code=400, detail=str(error)) from error
```

Current state (measured):

- Status codes in use: **400 ×10, 404 ×6, 422 ×1** — not uniform.
- The 404-vs-400 split is sometimes a **string heuristic**:
  `status_code = 404 if "not found" in str(error).lower() else 400`
  (`routes/admin.py`).
- The domain layer has **only two** typed exceptions
  (`AccountAlreadyExistsError`, `RuntimeTradeThrottleExceededError` in
  `src/trading/domain/exceptions.py`); the vast majority of validation raises
  **bare `ValueError`**.
- A single app instance (`apps/paper_trading_web/backend/main.py`) with **no**
  exception handlers registered today.
- `services/exports.py` raises `HTTPException` *directly* as path-validation
  guard clauses — that is route-specific transport logic, a different concern
  from mapping a domain error.

Per the **UI Backend Boundary Rule**, this mapping legitimately belongs to the UI
transport layer — the issue is only that it is duplicated per route rather than
expressed once.

Options considered:

**A. A `@http_errors` decorator on route handlers.** A parametrized decorator
(e.g. `@http_errors({ValueError: 400})`) wrapping each route.
- Pros: localized to the UI layer; no domain changes; signature-preserving
  (`ParamSpec`) per ADR 006 §4.
- Cons: status still varies per route, so the decorator needs per-route config;
  it cannot cleanly express the 404-vs-400 split without re-encoding the string
  heuristic; modest dedup for the indirection added. A decorator is not clearly
  better than the explicit `try/except` here (ADR 006 §5).

**B. FastAPI app-level exception handlers keyed on typed domain exceptions.**
Register handlers once in `main.py` (`@app.exception_handler(NotFoundError)` →
404, `@app.exception_handler(ValidationError)` → 400), and have domain/services
raise those typed exceptions instead of bare `ValueError`.
- Pros: removes **all** per-route `try/except`; one source of truth; eliminates
  the string heuristic; idiomatic FastAPI.
- Cons: requires introducing a domain exception taxonomy and refactoring service
  call sites to raise it — a cross-layer investment. A naive
  `@app.exception_handler(ValueError) → 400` catch-all would carry the **same
  masking risk we rejected for the CLI handlers**: it would turn *any* `ValueError`
  (including genuine bugs that should surface as 500) into a 400. Avoiding that is
  exactly why the typed taxonomy is required.

**C. Phased adoption of B.** (1) Add a `NotFoundError` (and as needed
`ValidationError`/`ConflictError`) to `src/trading/domain/exceptions.py`; (2)
register app-level handlers mapping those types → 404/400/409; (3) migrate the
heuristic and per-route catches as their underlying services adopt the typed
exceptions; (4) leave genuinely route-specific `HTTPException` guards (e.g.
`exports.py` path validation) in place.

## Decision

**Recommended: Option C (phased Option B), pending acceptance.** Typed
domain exceptions mapped by app-level handlers is the correct end state; the
phased path lets the taxonomy grow with the call sites it serves and avoids a
big-bang refactor. Explicitly **reject** a blanket `ValueError → 400` handler:
only typed exceptions are mapped, so an unexpected `ValueError` still surfaces as
500 rather than masquerading as a client error (consistent with the cli/handlers
decision).

Option A (decorator) is **not** recommended: it adds indirection without
resolving the status variance, and ADR 006 §5 favors the plainest tool.

### Phase 1 — implemented

Accepted and shipped as the first slice:

- `NotFoundError(ValueError)` added to `src/trading/domain/exceptions.py`. It
  subclasses `ValueError` so existing `except ValueError` handlers (CLI, UI
  validation, tests) keep working unchanged, while the UI can match the type for
  404. A bare `ValueError` still surfaces as 500.
- The user-facing entity-lookup not-found sources now raise it:
  `services/accounts/mutations.get_account`, `backtesting/services/report_service`,
  `backtesting/repositories/walk_forward_repository` (backtest run),
  `backtesting/services/walk_forward_report_service` (group),
  `services/autonomy_monitor/queries`, `services/admin/deletions`, and
  `services/promotion/actions._fetch_review_or_raise`.
- One app-level handler in `apps/paper_trading_web/backend/main.py`:
  `NotFoundError -> 404`.
- The not-found-only routes dropped their local 404 mapping
  (`routes/backtests.py`, `routes/autonomy_monitor.py`,
  `services/accounts/data_access.require_account_row`), and
  `services/admin.delete_managed_account` dropped its
  `"Accounts not found:"` string heuristic — all now rely on the app handler.

**Conversion principle.** Only "a requested entity does not exist" (a lookup
miss) becomes `NotFoundError`. Deliberately left as `ValueError`: *bad input*
(`backtest_data_service` bad directory path, `csv_export` invalid table — 400
-class) and *internal post-write integrity* checks (`repositories/promotion`
"not found after insert", `services/promotion/actions` "not found after request
creation", `services/books/accounting` fill-processing invariants — 500-class,
not user not-found).

### Phase 2 — implemented

The second slice completes the migration for the remaining per-route
`ValueError` catches:

- `ValidationError(ValueError)` added to `src/trading/domain/exceptions.py`
  (sibling of `NotFoundError`; both subclass `ValueError` so existing
  `except ValueError` callers — CLI, tests — are unchanged). A second app-level
  handler in `apps/paper_trading_web/backend/main.py` maps `ValidationError -> 400`.
- User-input validation raises reachable from the migrated routes now raise
  `ValidationError`: `services/accounts/config.py` (enum/range/sizing/option
  checks), `services/accounts/mutations.py` and `queries.py` (empty-name,
  positive-id/limit, `initial_cash > 0`), `domain/strategy_signals.py`
  (unknown-strategy), `backtesting/domain/windowing.py` and
  `backtesting/services/backtest_data_service.py` (date/lookback/universe
  checks), and `services/profiles/rotation_config_parser.py` (rotation object
  shape, lookback, schedule strategy names).
- Routes dropped their blanket `except ValueError -> 400`: `routes/backtests.py`
  (run/preflight/walk-forward), `routes/admin.py` (create account). The account
  params route (`routes/accounts.py`) narrowed its catch to
  `except ValidationError -> 422`, preserving that route-specific status.
- The `routes/admin.py` promotion-overview `"not found"` string heuristic was
  removed: a missing account already raises `NotFoundError` (from `get_account`),
  which the app handler maps to 404.
- The account-create service wrapper (`backend/services/admin.py`) now translates
  the domain `AccountAlreadyExistsError` to `ValidationError` (duplicate name is
  caller-correctable input -> 400); it no longer flattens arbitrary `ValueError`,
  so unexpected errors surface as 500.

**Conversion principle (unchanged).** Only user-input validation becomes
`ValidationError`. Deliberately left as bare `ValueError` -> 500: backtest
domain-math invariants (`backtesting/domain/metrics.py`,
`simulation_math.py`, `execution_service.py`), internal post-write integrity
checks, and the generic `domain/rotation.py` list parser (also used on
DB-sourced data, where a failure is an integrity error, not user input).
Route-specific transport guards stay direct `HTTPException`: the preflight
`FileNotFoundError -> 400` (missing tickers file) and `services/exports.py`
path validation.

**Deferred.** No `ConflictError`/409 was introduced — a duplicate account
stays 400, preserving the prior client contract. It can be added later if a
409 is wanted for conflict cases.

## Consequences

If accepted (Option C):

- Per-route `try/except → HTTPException` collapses to typed `raise` in
  services + a handful of app-level handlers; the 404 string heuristic is removed.
- Domain gains a small, reusable exception taxonomy (also usable by CLI/runtime).
- Route tests asserting specific 400/404 codes continue to pass (status mapping
  is preserved), but service call sites change from `raise ValueError` to typed
  raises — a cross-layer edit per migrated path.
- Migration is incremental and per-service; do not batch it with unrelated work.

If deferred: leave the per-route mapping as-is. It is duplicated but explicit,
correct, and confined to the transport layer — an acceptable resting state.
