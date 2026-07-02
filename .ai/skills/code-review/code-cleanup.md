---
name: code-cleanup
description: Refactor Python, frontend, or mixed code for readability, maintainability, and cleaner boundaries without changing intended behavior.
---

# Code Cleanup

Use this skill for behavior-preserving refactors across backend, frontend, or mixed scope.

## Workflow

1. Identify the main complexity drivers in scope.
2. Simplify tangled logic, extract helpers where they clarify intent, and remove duplication.
3. Preserve type safety, public contracts, and layer boundaries.
4. Update tests when moved logic is behavior-sensitive.
5. Check the touched scope for obsolete helpers, duplicate serializers, compatibility shims, dead types, stale tests, and docs or routes that still describe prior behavior.
6. Classify cleanup candidates as:
   - `safe to remove now`
   - `needs targeted verification`
   - `intentional compatibility path`
   - `defer/backlog`

## Scope guidance

- Use for Python-only cleanup in `src/trading/` or `apps/paper_trading_web/backend/`.
- Use for frontend-only cleanup in `apps/paper_trading_web/frontend/`.
- Use for mixed backend and frontend refactors when the primary goal is cleanup rather than contract debugging.

## Constraints

- Do not change business or user-visible behavior unless requested.
- Do not add abstraction for its own sake.
- Do not loosen types to make refactors easier.
- Read `docs/architecture/architecture-conventions.md` before editing `src/trading/`.
- Do not remove code based on name alone. Require no references, or references that can be safely migrated inside the task.
- Keep cleanup advisory by default; avoid broad unrelated removals unless the obsolete path is directly in scope and validation proves removal is safe.

## Repo references

- `docs/architecture/architecture-conventions.md`
- `docs/conventions/general-style.md`
- `docs/conventions/python-style.md`
- `src/trading/`
- `apps/paper_trading_web/backend/`
- `apps/paper_trading_web/frontend/`
- Python tests under `tests/`
- Frontend tests under `apps/paper_trading_web/frontend/src/tests/`

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
5. Developer verification instructions
6. Cleanup/robustness notes with candidate classification
