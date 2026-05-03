# Paper Trading UI Refactor Progress

Last updated: 2026-05-02

## Scope

Track cleanup/refactor progress for `paper_trading_ui/` and keep a concrete
restart point for the next session.

## Completed So Far

- Backend service layout has been normalized into clearer ownership buckets:
  - `backend/services/accounts/`
  - `backend/services/features/`
  - `backend/services/operations/`
- Backend tests were moved into matching subfolders and split by responsibility:
  - `tests/paper_trading_ui/backend/routes/...`
  - `tests/paper_trading_ui/backend/services/...`
  - legacy `tests/paper_trading_ui/backend/route_functions/...` was retired after route coverage was folded into API route tests
- Frontend type ownership was decomposed from a broad barrel into focused files:
  - `frontend/src/types/accounts.ts`
  - `frontend/src/types/backtesting.ts`
  - `frontend/src/types/admin.ts`
  - `frontend/src/types/compare.ts`
  - `frontend/src/types/signals.ts`
- Account detail frontend rendering was split into smaller modules:
  - `frontend/src/components/account-detail/config-editor.ts`
  - `frontend/src/components/account-detail/config-summary.ts`
  - `frontend/src/components/account-detail/config-options.ts`
  - `frontend/src/components/account-detail/sections-header.ts`
  - `frontend/src/components/account-detail/sections-overview.ts`
  - `frontend/src/components/account-detail/sections-ledger.ts`
  - `frontend/src/components/account-detail/sections-snapshots.ts`
  - stable entrypoints kept in `config.ts` and `sections.ts`
- Frontend checks passed after the account-detail split:
  - `npm run lint`
  - `npm run typecheck`
  - `npm run test` (84 passing)
  - `npm run build`

## Remaining High-Value Review Areas

1. Frontend test decomposition (largest files):
   - `frontend/src/tests/components/detail.test.ts` (~442 lines)
   - `frontend/src/tests/components/backtesting.test.ts` (~249 lines)
2. Accounts route test readability:
   - `tests/paper_trading_ui/backend/routes/accounts/test_accounts_routes.py`
   - keep route-level scenarios focused and avoid redundant direct route-function variants
3. Backend service cleanup hotspots:
   - `backend/services/accounts/summaries.py` (~224 lines)
   - `backend/services/features/shared.py` (~186 lines)
4. Frontend feature/component readability hotspots:
   - `frontend/src/features/backtesting/controller.ts` (~309 lines)
   - `frontend/src/features/accounts/detail.ts` (~258 lines)
   - `frontend/src/features/admin/accounts.ts` (~253 lines)
   - `frontend/src/components/admin-ops.ts` (~212 lines)
5. CSS consolidation and boundaries:
   - `frontend/src/styles/admin.css` (~411 lines)
   - `frontend/src/styles/accounts.css` (~398 lines)
   - `frontend/src/styles/docs.css` (~370 lines)
   - `frontend/src/styles/runtime.css` (~270 lines)

## Notes To Preserve

- Keep the existing route-function test strategy in mind for environments where
  sync FastAPI client behavior can stall. Context is documented in
  `tests/paper_trading_ui/MEMORY.md`.
- Continue favoring behavior-preserving refactors with stable public module
  entrypoints while splitting large internals.

## Proposed Next Session Start

1. Re-run frontend baseline checks (`lint`, `typecheck`, `test`, `build`).
2. Split `detail.test.ts` into section-focused test files.
3. Split `backtesting.test.ts` into scenario-focused test files.
4. Continue tightening accounts-route test readability and fixture clarity.
5. Reassess backend service hotspots and pick the next 1-2 bounded files.
