---
name: Code Review
layer: portable
description: Portable starter skill for reviewing changed files for regressions, missing tests, API drift, and boundary violations.
use_when:
  - before commit or merge
  - after a multi-file refactor
  - when evaluating whether a change is ready
localize_with:
  - validation commands
  - project architecture rules
  - code ownership boundaries
---

## Goal

Provide a high-signal review focused on correctness, safety, and maintainability.

## Responsibilities

1. Survey the diff and identify changed surfaces.
2. Check for regressions, contract drift, and missing coverage.
3. Cross-reference architecture rules and safety constraints.
4. Report only supported findings with file and line evidence.

## Constraints

1. Do not implement fixes inside the review.
2. Do not inflate severity for style-only comments.
3. Do not report unsupported guesses.

## Localize for a project

Fill in:

- read-only git commands or diff tooling
- validation commands for Python, frontend, or both
- repo-specific safety rules that should block a change

## Expected output

1. Verdict
2. Findings by severity
3. Validation summary
4. Short overall risk summary
