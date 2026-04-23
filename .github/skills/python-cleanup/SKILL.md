---
name: python-cleanup
description: Improve Python readability, modularity, and maintainability without changing intended behavior.
---

# Python Cleanup

Use this skill for behavior-preserving Python refactors.

## Workflow

1. Simplify overly large or tangled code paths.
2. Extract helpers when doing so reduces duplication or clarifies intent.
3. Preserve type safety and surrounding conventions.
4. Add or adjust tests when moved logic is behavior-sensitive.

## Constraints

- Do not change business behavior unless requested.
- Do not add abstraction for its own sake.
- Do not bypass type checks with unsafe casts.

## Repo references

- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `trading/`
- `paper_trading_ui/backend/`
- Python test suites under `tests/`

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
