---
name: code-review
description: Review a diff or larger code area for regressions, missing tests, API drift, stale code, redundancy, and architecture or safety violations.
---

# Code Review

Use this skill for read-only review of a diff, branch, or focused area, including broad subsystem audits.

## Workflow

1. Run or inspect deterministic context first:
   - `python -m scripts.checks.review_scope_check --base <base_ref>` for branch reviews, or without `--base` for local changes.
   - `validate-code` results for lint, type, tests, layer, and safety checks.
2. Survey the changed surface using the suggested mode/high-risk triggers.
3. Review residual judgment areas: behavior regressions, semantic contract drift, missing edge-case coverage, wrong ownership that static layer checks cannot catch, and safe-removal risk.
4. When the scope is broad, look for stale paths, redundant implementations, and simplification opportunities.
5. For stale-code or obsolescence claims, collect evidence from reference searches, public API/route/type usage, tests covering old and new paths, and migration or backward-compatibility risk.
6. Report only supported findings with file and line evidence.

## Modes

- **Baseline** (lightweight): survey changed files, check correctness and contract drift, cross-check architecture rules. Report only hard findings. No stale-code or cleanup sweep.
- **Standard**: same as Baseline plus — when scope is broad, look for stale paths, redundant implementations, and simplification opportunities.
- **Deep**: Standard plus explicit sweep for stale code, redundancy, schema relevance, canonical-path drift, and cleanup opportunities beyond the diff.

## Constraints

- Do not implement fixes during the review.
- Do not report deterministic lint/type/layer/test failures as AI findings unless they reveal a separate judgment-based risk.
- Do not elevate style-only comments into findings.
- Do not report guesses without evidence.
- Keep broader cleanup recommendations evidence-based and separate from hard defects.
- Treat cleanup as advisory by default. Do not recommend removal without usage evidence and a compatibility risk assessment.

## Repo references

- `AGENTS.md`
- `docs/architecture/architecture-conventions.md`
- `docs/conventions/general-style.md`
- `docs/conventions/python-style.md`
- Relevant schema and migration files when database concerns are in scope
- Repo validation commands from `scripts/run_checks.py` and `scripts/checks/`

## Expected output

1. Findings by severity
2. Cleanup or simplification opportunities when relevant
3. Validation summary
4. Developer verification guidance when implementation effects are reviewed
5. Short overall risk summary
