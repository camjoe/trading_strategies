---
name: code-review
description: Review changed files for regressions, missing tests, API drift, and architecture or safety violations.
---

# Code Review

Use this skill for read-only review of a diff, branch, or focused area.

## Workflow

1. Survey the changed surface.
2. Check for correctness risks, contract drift, and missing coverage.
3. Cross-check architecture and safety rules that apply in this repo.
4. Report only supported findings with file and line evidence.

## Constraints

- Do not implement fixes during the review.
- Do not elevate style-only comments into findings.
- Do not report guesses without evidence.

## Repo references

- `AGENTS.md`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Repo validation commands from `scripts/run_checks.py` and `scripts/checks/`

## Expected output

1. Findings by severity
2. Validation summary
3. Short overall risk summary
