---
name: deep-code-review
description: Perform a broad, read-only audit of a subsystem for simplification, stale code, redundancy, schema relevance, and architecture quality.
---

# Deep Code Review

Use this skill for whole-area review beyond the current diff.

## Workflow

1. Identify duplication, parallel implementations, and extraction opportunities.
2. Detect stale or superseded code paths.
3. Review abstraction quality, ownership, and dependency direction.
4. Check whether schema elements and feature surfaces still appear justified.
5. Separate high-confidence cleanup candidates from hypotheses that need confirmation.

## Constraints

- Keep the review read-only and evidence-based.
- Do not recommend deletion without usage evidence or explicit uncertainty.
- Optimize for simpler systems, not just fewer lines.

## Review dimensions

- Simplification
- Redundancy
- Stale or superseded code
- Generalization opportunities
- Schema relevance
- Canonical-path drift
- Config/default drift
- Architecture quality
- Human legibility

## Repo references

- `AGENTS.md`
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Relevant schema and migration files when database concerns are in scope

## Expected output

1. Scope and review method
2. Prioritized findings
3. Remediation roadmap with confidence notes
