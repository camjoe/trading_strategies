---
name: architecture-review
description: Review module boundaries, dependency direction, layering, and code placement decisions in this repository or a similar application codebase.
---

# Architecture Review

Use this skill when the task is primarily about structure rather than implementation detail.

## Workflow

1. Run or inspect `python -m scripts.checks.review_scope_check` for changed-file classification.
2. Classify each changed or reviewed module by responsibility.
3. Use `validate-code` / `layer_check` for mechanical import-boundary failures.
4. Check residual dependency direction, layer ownership, and wrong-layer logic that static imports cannot detect.
5. Recommend the correct target layer for questionable changes.

## Constraints

- Focus on architecture, not style.
- Do not excuse boundary violations just because tests pass.
- Read the repo's architecture conventions before editing `src/trading/`.

## Repo references

- `docs/architecture/architecture-conventions.md`
- `AGENTS.md`
- `scripts/checks/review_scope_check.py`

## Expected output

1. Boundary summary
2. Violations or risks
3. Correct target layer for each questionable change
