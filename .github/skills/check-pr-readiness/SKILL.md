---
name: pr-readiness
description: Full pre-PR readiness workflow. Runs deterministic checks (layer, lint, tests), then AI code review and architecture review, then generates a PR readiness report.
---

# PR Readiness Workflow

Use this skill to run the complete pre-PR gatekeeping process before submitting a pull request.

## What this skill does

Runs five ordered steps, stopping at the first failure and reporting what needs to be fixed.

| Step | Type | What runs |
|---|---|---|
| 1 | Deterministic | Layer boundary check |
| 2 | Deterministic | Ruff lint + mypy type check |
| 3 | Deterministic | Branch-targeted pytest (vs base ref) |
| 4 | AI | Code review — style, quality, correctness, missing tests |
| 5 | AI | Architecture review — layering, coupling, maintainability |
| Report | AI | PR readiness report saved to `local/pr_readiness_report.md` |

Steps 1–3 are purely deterministic (no tokens). Steps 4–5 are scoped tightly to the branch diff to minimize token usage.

## Invocation

This skill is invoked by the `pr ready` shortcut in `AGENTS.md`.

```
pr ready               # vs develop (default)
pr ready: main         # vs custom base
pr ready: origin/main
```

## Workflow

### Phase 1 — Deterministic gate

Run the deterministic check script:

```
python -m scripts.checks.pr_ready --base <base_ref>
```

- Default base: `develop`
- If the command exits non-zero, **stop immediately** and report which step failed with the error output. Do not proceed to AI steps until Phase 1 passes.

### Phase 2 — Code review (AI, scoped to branch diff)

Run a lean code review focused on style, quality, correctness, and missing tests.

Constraints:
- Scope: only files changed in the branch vs `<base_ref>` (use `git diff --name-only <base_ref>...HEAD`)
- Do NOT review files that have no branch changes
- Focus: style violations, logic errors, missing test coverage, API contract drift
- Do not report on architecture concerns here (that is Phase 3)
- Severity: HIGH findings block the PR; LOW findings are advisory
- Token economy: be concise. No lengthy prose. Finding + file:line + one-sentence explanation.

Reference: `.github/skills/code-review/SKILL.md`, `.github/BOT_STYLE_GUIDE.md`

### Phase 3 — Architecture review (AI, scoped to branch diff)

Run a lean architecture review focused on layering, coupling, and placement.

Constraints:
- Scope: only files changed in the branch
- Focus: layer boundary violations, dependency direction, logic in wrong layer, maintainability concerns
- Do NOT repeat style findings already caught in Phase 2
- Severity: VIOLATION findings block the PR; CONCERN findings are advisory
- Token economy: be concise. Finding + file:line + one-sentence explanation.

Reference: `.github/skills/architecture-review/SKILL.md`, `.github/BOT_ARCHITECTURE_CONVENTIONS.md`

### Phase 4 — Report

Generate the PR readiness report.

1. Print the report to the terminal.
2. Save it to `local/pr_readiness_report.md` (create `local/` if it doesn't exist).
3. Report format:

```markdown
## PR Readiness Report

**Branch:** <current branch name>
**Base:** <base_ref>
**Date:** <YYYY-MM-DD>

---

### Step 1–3: Deterministic Checks

| Check | Result |
|---|---|
| Layer boundaries | ✅ Clean / ❌ FAILED |
| Ruff + Mypy | ✅ Clean / ❌ FAILED |
| Tests | ✅ N tests, M suites / ❌ FAILED / ⏭️ No changed suites |

---

### Step 4: Code Review

<findings grouped by severity, or "✅ No issues found.">

---

### Step 5: Architecture Review

<findings grouped by severity, or "✅ No issues found.">

---

### Overall: ✅ READY / ❌ NOT READY

<one-sentence summary of blocking issues if NOT READY, or "No blocking issues found." if READY>
```

## Constraints

- Stop at the first blocking failure. Do not run AI steps if Phase 1 fails.
- Only surface HIGH/VIOLATION findings as blockers. LOW/CONCERN findings are advisory.
- Do not implement fixes during this skill. Report only.
- Do not report on unchanged files.
- Keep findings concise — this is a gate report, not a code review essay.

## Repo references

- `scripts/checks/pr_ready.py` — deterministic gate script
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `.github/BOT_STYLE_GUIDE.md`
- `docs/style/python-style-guide.md`
- `AGENTS.md`
