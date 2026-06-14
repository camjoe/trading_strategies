---
name: check-pr-readiness
description: Runs the full pre-PR gatekeeping workflow: deterministic checks (layer, lint, tests), then AI code review and architecture review, then saves a readiness report. Use when preparing to submit a pull request or when asked to run a PR readiness check.
---

# Checking PR Readiness

Runs five ordered steps, stopping at the first failure.

| Step | Type | What runs |
|---|---|---|
| 1–3 | Deterministic | Layer check, ruff + mypy, branch-targeted tests |
| 4 | AI | Code review — style, quality, correctness, missing tests |
| 5 | AI | Architecture review — layering, coupling, maintainability |
| Report | AI | Saved to `local/pr_readiness_report.md` + printed |

Steps 1–3 are AI-free. Steps 4–5 are scoped to the branch diff only to minimize token usage.

## Invocation

```
pr ready               # vs develop (default)
pr ready: main         # vs custom base
```

## Phase 1 — Deterministic gate

```
python -m scripts.checks.pr_ready --base <base_ref>
```

If exit code is non-zero, **stop**. Report which step failed. Do not proceed to Phase 2.

See [validate-code skill](../validate-code/SKILL.md) for individual check commands.

## Phase 2 — Code review

Scope: `git diff --name-only <base_ref>...HEAD` only. No unrequested scope expansion.

Focus: style violations, logic errors, missing test coverage, API contract drift.
Do NOT surface architecture concerns here (Phase 3 handles those).

Severity: HIGH = blocks PR. LOW = advisory.
Be concise: finding + file:line + one sentence.

Reference: [code-review.md](../code-review/code-review.md), `.github/BOT_STYLE_GUIDE.md`

## Phase 3 — Architecture review

Scope: same changed files only.

Focus: layer boundary violations, dependency direction, wrong-layer logic, coupling concerns.
Do NOT repeat style findings from Phase 2.

Severity: VIOLATION = blocks PR. CONCERN = advisory.
Be concise: finding + file:line + one sentence.

Reference: [architecture-review.md](../code-review/architecture-review.md), `.github/BOT_ARCHITECTURE_CONVENTIONS.md`

## Phase 4 — Report

Print to terminal and save to `local/pr_readiness_report.md`.

```markdown
## PR Readiness Report

**Branch:** <branch>  **Base:** <base_ref>  **Date:** <YYYY-MM-DD>

### Deterministic Checks
| Check | Result |
|---|---|
| Layer boundaries | Clean / FAILED |
| Ruff + Mypy | Clean / FAILED |
| Tests | N tests, M suites / FAILED / No changed suites |

### Code Review
<findings by severity, or "No issues found.">

### Architecture Review
<findings by severity, or "No issues found.">

### Overall: READY / NOT READY
<one sentence: blocking issues or "No blocking issues found.">
```

## Constraints

- Stop at the first blocking failure. Do not run AI steps if Phase 1 fails.
- HIGH/VIOLATION findings block. LOW/CONCERN are advisory.
- Do not implement fixes. Report only.
- Do not report on unchanged files.

## Repo references

- `scripts/checks/pr_ready.py`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `.github/BOT_STYLE_GUIDE.md`
- `AGENTS.md`
