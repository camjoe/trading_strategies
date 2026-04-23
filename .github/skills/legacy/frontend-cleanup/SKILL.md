---
name: frontend-cleanup
description: Simplify TypeScript or frontend UI code while preserving behavior, readability, and type safety.
---

# Frontend Cleanup

Use this skill for frontend-only cleanup and refactoring.

## Workflow

1. Simplify tangled component, state, and rendering logic.
2. Remove duplication and clarify data-flow boundaries.
3. Preserve or improve type safety.
4. Update related tests when behavior-sensitive logic moves.

## Constraints

- Do not change user-visible behavior unless requested.
- Do not loosen types to make refactors easier.
- Do not introduce broad style-only churn.

## Repo references

- `paper_trading_ui/frontend/`
- Frontend tests under `paper_trading_ui/frontend/src/tests/`
- Frontend validation commands from `package.json`

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
