---
name: Python Cleanup
layer: portable
description: Portable starter skill for improving Python readability, modularity, and maintainability without changing intended behavior.
use_when:
  - refactoring large functions or modules
  - reducing complexity
  - making backend code easier to review and extend
localize_with:
  - lint and type-check commands
  - architecture rules
  - testing conventions
---

## Goal

Improve Python code quality while preserving current behavior and public contracts.

## Responsibilities

1. Simplify overly large or tangled code paths.
2. Extract helpers where it reduces duplication or clarifies intent.
3. Keep type safety and existing conventions intact.
4. Add or adjust tests when behavior-sensitive logic moves.

## Constraints

1. Do not change business behavior unless the task explicitly requires it.
2. Do not replace clear code with abstraction for its own sake.
3. Do not bypass type checks with unsafe casts.

## Localize for a project

Fill in:

- the repo's Python style and type-check expectations
- the correct layers for orchestration, policy logic, and persistence
- the available validation commands

## Expected output

1. Cleanup summary
2. Files changed
3. Behavior-preservation notes
4. Validation commands used
