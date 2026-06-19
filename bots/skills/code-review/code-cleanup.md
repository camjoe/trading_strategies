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

## Scope guidance

- Use for Python-only cleanup in `trading/` or `paper_trading_ui/backend/`.
- Use for frontend-only cleanup in `paper_trading_ui/frontend/`.
- Use for mixed backend and frontend refactors when the primary goal is cleanup rather than contract debugging.

## Constraints

- Do not change business or user-visible behavior unless requested.
- Do not add abstraction for its own sake.
- Do not loosen types to make refactors easier.
- Read `docs/architecture/architecture-conventions.md` before editing `trading/`.

## Repo references

- `docs/architecture/architecture-conventions.md`
- `docs/conventions/style-guide.md`
- `docs/conventions/python-style.md`
- `trading/`
- `paper_trading_ui/backend/`
- `paper_trading_ui/frontend/`
- Python tests under `tests/`
- Frontend tests under `paper_trading_ui/frontend/src/tests/`

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
