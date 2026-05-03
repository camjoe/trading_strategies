---
name: test-expansion
description: Increase test coverage depth, edge-case coverage, and regression protection without adding low-value tests.
---

# Test Expansion

Use this skill when testing is the primary objective.

## Workflow

1. Identify weakly tested logic in scope.
2. Add happy-path, edge-case, and failure-path coverage as appropriate.
3. Prefer focused behavior assertions over incidental implementation checks.
4. Add regression tests for bugs or fragile workflows.

## Constraints

- Do not pad coverage with low-value tests.
- Do not change production behavior unless needed and approved to make code testable.
- Do not ignore error paths for critical workflows.

## Repo references

- `tests/`
- `paper_trading_ui/frontend/src/tests/`
- `pytest.ini`
- `paper_trading_ui/frontend/package.json`

## Expected output

1. Coverage gaps addressed
2. New tests added
3. Remaining risk areas
