---
name: code-review
description: Reviews code changes for behavioral regressions, architecture and ownership issues, contract drift, missing test evidence, and cleanup risk. Use when asked to review a diff, branch, PR, codebase area, or cleanup/refactor.
---

# Code Review

Use this skill for read-only review. Do not implement fixes during review.

## Deterministic Context

Consult deterministic checks first when available:

```sh
python -m scripts.checks.repo.review_scope_check --base <base_ref>
python -m scripts.run_checks pr --base <base_ref>
```

Do not duplicate deterministic lint, type, layer, safety, or test failures as AI findings unless the script passed and there is a subtler judgment-based issue.

## Modes

Choose the lightest mode that fits the request and classifier output:

| Mode | Use when | Focus |
|---|---|---|
| Baseline | quick check, low-risk pre-merge | hard defects only |
| Standard | normal diff/branch review | behavior, contracts, tests, maintainability |
| Aggressive | runtime, broker, database, admin, scheduler, or "deep" review | negative paths, rollback/compatibility, safety, zero-findings evidence |
| Architecture | layering, ownership, placement, dependency direction | wrong-layer logic beyond static import checks |
| Contract | frontend/backend/API/schema changes | request/response shape, nullability, route semantics, UI assumptions |
| Cleanup | refactor, simplification, stale-code audit | safe removal evidence, duplication, compatibility risk |
| PR | called from `check-pr-readiness` | one Architecture and conventions section; the lenses run separately |

`review_scope_check` only suggests `standard`, `aggressive`, `architecture`, or `contract`, plus the reviewers a diff needs (see Lenses). Treat documentation and skill changes as scope notes, not review modes.

## Review Focus

AI review should cover what scripts cannot prove:

- Behavioral regressions and edge cases.
- Semantic contract drift, especially API payload meaning and nullability.
- Wrong ownership despite legal imports.
- Missing test evidence for important behavior paths.
- Unjustified abstractions, excessive coupling, or unnecessary complexity.
- Source narration: comments or docstrings that record the author's reasoning, the change's
  history, or restated commit-message prose instead of facts about the system. A diff adding more
  prose lines than code lines is the usual tell.
- Stale paths or cleanup candidates with reference-search evidence and compatibility risk.
- High-risk safety gaps not covered by mechanical checks.

Do not flag TODO/comment *style* by itself — formatting, punctuation, or one-line phrasing. Narration is a separate, in-scope finding: report it when commentary explains the author's reasoning or the change's history rather than the system's behavior. Do not report style-only nits unless they materially harm readability or maintenance.

## Lenses

Independent, read-only reviews by fresh-context agents: Architecture and conventions, and four
lenses (Break it, Operator, Test skeptic, Simplifier). Severity definitions, the rules every reviewer
follows, each reviewer's checklist, and how the orchestrator runs them are in [lenses.md](lenses.md).
`review_scope_check` prints which reviewers a diff needs.

## PR Mode

For PR readiness, produce one section, **Architecture and conventions**, scoped to
`git diff --name-only <base_ref>...HEAD`. Follow the Architecture and conventions section of
[lenses.md](lenses.md) and run it as a fresh-context read-only reviewer. Ignore anything ruff,
mypy, or the layer check reports.

Each finding format, with severity BLOCKER, CONCERN, or NOTE (defined in [lenses.md](lenses.md)):

```text
SEVERITY | path/to/file.py:42 | concise evidence-backed issue
```

No findings:

```text
Architecture and conventions: Clean
```

Behavior, tests, and simplification are not reviewed here; the lenses cover them.

## Output

For general review:

1. Findings first, rated BLOCKER, CONCERN, or NOTE and ordered by severity, with file and line evidence.
2. Risks/concerns when material but not defects.
3. Cleanup opportunities when relevant, classified as:
   - `safe to remove now`
   - `needs targeted verification`
   - `intentional compatibility path`
   - `defer/backlog`
4. Validation summary: commands checked or not run.
5. Developer verification guidance.
6. Short overall risk summary.

## Constraints

- Scope review to changed files unless the selected mode explicitly expands it.
- Do not report guesses without evidence.
- Do not recommend removal without usage evidence and compatibility risk assessment.
- Keep cleanup advisory by default unless directly tied to the reviewed change and proven safe.

## Repo References

- `scripts/checks/repo/review_scope_check.py`
- `scripts/run_checks.py`
- `docs/architecture/architecture-conventions.md`
- `docs/conventions/general-style.md`
- `docs/conventions/python-style.md`
