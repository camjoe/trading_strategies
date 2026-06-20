---
name: architecture-review
description: Review module boundaries, dependency direction, layering, and code placement decisions in this repository or a similar application codebase.
---

# Architecture Review

Use this skill when the task is primarily about structure rather than implementation detail.

## Workflow

1. Classify each changed or reviewed module by responsibility.
2. Check dependency direction, import boundaries, and layer ownership.
3. Flag logic that appears to live in the wrong layer.
4. Recommend the correct target layer for questionable changes.

## Constraints

- Focus on architecture, not style.
- Do not excuse boundary violations just because tests pass.
- Read the repo's architecture conventions before editing `trading/`.

## Repo references

- `docs/architecture/architecture-conventions.md`
- `AGENTS.md`

## Expected output

1. Boundary summary
2. Violations or risks
3. Correct target layer for each questionable change
