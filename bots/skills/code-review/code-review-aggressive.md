---
name: code-review-aggressive
description: Deep, high-scrutiny review focused on defects, residual risk, stale code, and test adequacy with explicit zero-findings evidence.
---

# Code Review Aggressive

Use this skill when quality bar should be higher than standard review, especially before PR.

## Workflow

1. Build a review map of changed behavior areas and touched subsystems.
2. Run standard defect checks for regressions, contract drift, and migration safety.
3. Run required negative-path checks:
   - invalid inputs
   - not-found and empty data handling
   - rollback or compatibility behavior
   - permission or safety guard regressions
4. Run required simplification checks:
   - stale compatibility paths
   - dead or redundant helpers
   - duplicate tests and fixtures
   - obsolete docs wording
5. Produce a test adequacy matrix for each changed behavior area:
   - existing tests
   - missing tests
   - commands run and outcome
6. If no hard defects are found, provide zero-findings evidence.

## High-risk triggers

Automatically switch to deep mode when any of these are touched:

- runtime jobs or schedulers
- broker adapters or live-trading guardrails
- account create/update/delete flows
- database migrations or schema init
- admin or operator routes

## Constraints

- Do not implement fixes during review.
- Do not report style-only nits as findings.
- Label uncertain items as `Risks/Concerns`, not defects.
- Every hard finding must include concrete file and line evidence.

## Repo references

- `AGENTS.md`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `trading/database/*` for schema and migration safety
- Repo validation commands from `scripts/run_checks.py` and `scripts/checks/`

## Expected output

1. Findings by severity (defects only)
2. Risks/Concerns (non-defect but material risk)
3. Zero-findings evidence checklist when Findings is empty
4. Test adequacy matrix
5. Cleanup and simplification opportunities
6. Validation summary
7. Short release-readiness verdict
