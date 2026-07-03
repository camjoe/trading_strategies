---
name: check-pr-readiness
description: Runs the full pre-PR gatekeeping workflow: deterministic checks (layer, lint, tests), then AI code review and architecture review, then saves a readiness report. Use when preparing to submit a pull request or when asked to run a PR readiness check.
invoker: any
---

# Checking PR Readiness

Runs six ordered steps. Stop at the first blocking failure — do not run subsequent AI steps if an earlier step fails.

| Step | Type | What runs | Stops on |
|---|---|---|---|
| 1 | Deterministic | Repo checks + Python lint/type/test checks | Any non-zero exit |
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
python -m scripts.run_checks repo
python -m scripts.run_checks python --base <base_ref>
```

Run the commands in order. If either exit code is non-zero, **stop immediately**. Report which command failed. Do not run Steps 2–6. Hand back to the user.

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

```
python -m scripts.run_checks docs --advisory
```

Runs documentation drift checks, including README consistency and generated reference-doc asset checks. Use `docs/maps/docs-map.md` ("Goes stale when" column) to map any changed source files to their owning docs. Never blocks the AI review workflow; collect findings for the report.

---

## Step 6 — PR readiness report

Print to terminal and save to `local/pr_readiness_report.md`.

```markdown
## PR Readiness Report

**Branch:** <branch>  **Base:** <base_ref>  **Date:** <YYYY-MM-DD>

### Step 1 — Deterministic Checks
| Check | Result |
|---|---|
| Repository checks | Clean / FAILED |
| Ruff | Clean / FAILED |
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

### Developer Verification Guide
<UI path, API endpoint, command/report path, or expected behavior a developer can use to inspect the result>

### Cleanup and Obsolescence Review
<obsolete code removed, cleanup candidates with evidence and classification, or "None found in touched scope">

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
- Preserve developer verification and cleanup/obsolescence notes in the saved report.
- Cleanup notes are advisory unless they identify a directly related obsolete path with safe removal evidence.

## Repo references

- `scripts/run_checks.py`
- `scripts/checks/repo_check.py`
- `scripts/checks/python_check.py`
- `docs/architecture/architecture-conventions.md`
- `docs/conventions/general-style.md`
- `AGENTS.md`
