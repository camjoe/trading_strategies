---
name: Frontend Cleanup
layer: portable
description: Portable starter skill for simplifying TypeScript or React frontend code while preserving behavior, readability, and type safety.
use_when:
  - cleaning up frontend-only code
  - reducing complexity in components or hooks
  - improving readability without changing UI behavior
localize_with:
  - frontend root path
  - lint, type-check, and test commands
  - UI architecture rules
---

## Goal

Make frontend code easier to read, modify, and review without changing intended behavior or weakening type safety.

## Responsibilities

1. Simplify tangled component, hook, and state-management logic.
2. Remove duplication and clarify rendering/data-flow boundaries.
3. Keep TypeScript types strong and aligned with the surrounding codebase.
4. Update related tests when behavior-sensitive refactors move logic.

## Constraints

1. Do not change user-visible behavior unless the task explicitly requires it.
2. Do not loosen types to make refactors easier.
3. Do not introduce broad style-only churn unrelated to readability or maintainability.

## Localize for a project

Fill in:

- the frontend root and key UI folders
- the lint, type-check, and test commands
- the repo's component, state, and API-contract conventions

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
