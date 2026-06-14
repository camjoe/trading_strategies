---
name: code-review-baseline
description: Baseline diff review for regressions, contract drift, and missing tests with evidence-backed findings only.
---

# Code Review Baseline

Use this skill for a standard read-only review of a diff, branch, or focused area.

## Workflow

1. Survey changed files and identify behavior changes.
2. Check for correctness risks, contract drift, and missing test coverage.
3. Cross-check architecture and safety rules for affected paths.
4. Report only supported findings with file and line evidence.

## Constraints

- Do not implement fixes during review.
- Do not elevate style-only comments into findings.
- Do not report guesses without evidence.

## Repo references

- `AGENTS.md`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Relevant schema and migration files when database concerns are in scope
- Repo validation commands from `scripts/run_checks.py` and `scripts/checks/`

## Expected output

1. Findings by severity
2. Optional cleanup opportunities
3. Validation summary
4. Short overall risk summary
