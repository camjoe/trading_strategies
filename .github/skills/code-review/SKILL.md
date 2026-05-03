---
name: code-review
description: Review a diff or larger code area for regressions, missing tests, API drift, stale code, redundancy, and architecture or safety violations.
---

# Code Review

Use this skill for read-only review of a diff, branch, or focused area, including broad subsystem audits.

## Workflow

1. Survey the changed surface.
2. Check for correctness risks, contract drift, and missing coverage.
3. When the scope is broad, look for stale paths, redundant implementations, and simplification opportunities.
4. Cross-check architecture and safety rules that apply in this repo.
5. Report only supported findings with file and line evidence.

## Modes

- Standard review: focus on regressions, correctness, contract drift, and missing tests.
- Deep review: expand to stale code, redundancy, schema relevance, canonical-path drift, and cleanup opportunities beyond the current diff.

## Constraints

- Do not implement fixes during the review.
- Do not elevate style-only comments into findings.
- Do not report guesses without evidence.
- Keep broader cleanup recommendations evidence-based and separate from hard defects.

## Repo references

- `AGENTS.md`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Relevant schema and migration files when database concerns are in scope
- Repo validation commands from `scripts/run_checks.py` and `scripts/checks/`

## Expected output

1. Findings by severity
2. Cleanup or simplification opportunities when relevant
3. Validation summary
4. Short overall risk summary
