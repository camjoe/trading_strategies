---
name: check-pr-readiness
description: Runs the full pre-PR gatekeeping workflow: deterministic checks (layer, lint, tests), then AI code review and architecture review, then saves a readiness report. Use when preparing to submit a pull request or when asked to run a PR readiness check.
---

# Checking PR Readiness

Runs six ordered steps. Stop at the first blocking failure — do not run subsequent AI steps if an earlier step fails.

| Step | Type | What runs | Stops on |
|---|---|---|---|
| 1 | Deterministic | Layer + lint + type check + tests | Any non-zero exit |
| 2 | AI | Architecture review (branch diff) | VIOLATION finding |
| 3 | AI | Style review (branch diff) | BLOCKER finding |
| 4 | AI | Quality review (branch diff) | BLOCKER finding |
| 5 | AI | Docs check (advisory) | Never |
| 6 | AI | PR readiness report | — |

Steps 2–4 are scoped to the branch diff only to minimize token usage.

## Invocation

```
pr ready               # vs develop (default)
pr ready: main         # vs custom base
```

---

## Step 1 — Deterministic gate

```
python -m scripts.checks.pr_ready --base <base_ref>
```

If exit code is non-zero, **stop immediately**. Report which check failed. Do not run Steps 2–6. Hand back to the user.

Reference: [validate-code/SKILL.md](../validate-code/SKILL.md)

---

## Step 2 — Architecture review

Reference: [code-review/pr-review-arch.md](../code-review/pr-review-arch.md)

- Scope: `git diff --name-only <base_ref>...HEAD` only.
- Severity: VIOLATION (blocks) vs CONCERN (advisory).
- If any VIOLATION found: **stop**. Do not run Steps 3–6. Print VIOLATION findings and hand back to user.

---

## Step 3 — Style review

Reference: [code-review/pr-review-style.md](../code-review/pr-review-style.md)

- Scope: same branch diff.
- Severity: BLOCKER (blocks) vs ADVISORY.
- If any BLOCKER found: **stop**. Do not run Steps 4–6. Print BLOCKER findings and hand back to user.

---

## Step 4 — Quality review

Reference: [code-review/pr-review-quality.md](../code-review/pr-review-quality.md)

- Scope: same branch diff.
- Severity: BLOCKER (blocks) vs ADVISORY.
- If any BLOCKER found: **stop**. Do not run Steps 5–6. Print BLOCKER findings and hand back to user.

---

## Step 5 — Docs check (advisory)

Reference: [update-documentation/docs-check.md](../update-documentation/docs-check.md)

```
python -m scripts.checks.readme_check
```

Never blocks. Collect findings for the report.

---

## Step 6 — PR readiness report

Print to terminal and save to `local/pr_readiness_report.md`.

```markdown
## PR Readiness Report

**Branch:** <branch>  **Base:** <base_ref>  **Date:** <YYYY-MM-DD>

### Step 1 — Deterministic Checks
| Check | Result |
|---|---|
| Layer boundaries | Clean / FAILED |
| Ruff + eslint/tsc | Clean / FAILED |
| Mypy | Clean / FAILED |
| Tests | N tests, M suites / FAILED / No changed suites |

### Step 2 — Architecture Review
<VIOLATION/CONCERN findings, or "Clean">

### Step 3 — Style Review
<BLOCKER/ADVISORY findings, or "Clean">

### Step 4 — Quality Review
<BLOCKER/ADVISORY findings, or "Clean">

### Step 5 — Docs Check (Advisory)
<staleness findings, or "No stale docs detected">

### Overall: READY / NOT READY
<one sentence: blocking issues or "No blocking issues found.">
```

---

## Constraints

- Do not run AI steps if Step 1 fails.
- Do not run Steps 3–6 if Step 2 has a VIOLATION.
- Do not run Steps 4–6 if Step 3 has a BLOCKER.
- Do not run Steps 5–6 if Step 4 has a BLOCKER.
- Do not implement fixes. Report only.
- Do not review unchanged files.

## Repo references

- `scripts/checks/pr_ready.py`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `.github/BOT_STYLE_GUIDE.md`
- `AGENTS.md`
