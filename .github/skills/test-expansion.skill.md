---
name: Test Expansion
layer: portable
description: Portable starter skill for increasing test coverage depth, edge-case coverage, and regression protection.
use_when:
  - new logic was added without enough tests
  - a bug needs a regression test
  - edge cases or failure paths are weakly covered
localize_with:
  - test runner commands
  - test file layout
  - project risk areas
---

## Goal

Make changes safer by improving meaningful automated coverage.

## Responsibilities

1. Identify untested or weakly tested logic in scope.
2. Add happy-path, edge-case, and failure-path coverage as appropriate.
3. Prefer focused, behavior-based assertions over incidental implementation checks.
4. Add regression tests for bugs or fragile workflows.

## Constraints

1. Do not pad coverage with low-value tests.
2. Do not change production behavior unless needed to make logic testable and approved.
3. Do not ignore error paths for critical workflows.

## Localize for a project

Fill in:

- pytest, vitest, or other test commands
- naming conventions and fixture patterns
- areas where regressions are especially expensive

## Expected output

1. Coverage gaps addressed
2. New tests added
3. Remaining risk areas
