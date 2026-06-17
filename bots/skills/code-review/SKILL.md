---
name: code-review
description: Reviews code changes for regressions, style violations, architecture boundary violations, missing tests, and contract drift. Use when asked to review a diff, branch, PR, codebase area, or when code quality, correctness, or safety should be evaluated.
invoker: any
---

# Code Review

## Choose a mode

| Mode | Use when | Reference |
|---|---|---|
| Standard | General PR or diff review | [code-review.md](code-review.md) |
| Baseline | Quick pre-merge check, low-risk changes — hard findings only | [code-review.md](code-review.md) (Baseline mode) |
| Aggressive | High-risk changes: runtime, broker, migrations, admin routes | [code-review-aggressive.md](code-review-aggressive.md) |
| Architecture | Layering, coupling, module placement, dependency direction | [architecture-review.md](architecture-review.md) |
| Cleanup | Behavior-preserving refactor, dead code, simplification | [code-cleanup.md](code-cleanup.md) |
| Contract | Frontend/backend API contract, route/schema alignment | [ui-api-contract.md](ui-api-contract.md) |
| PR Review | Pre-PR pass: arch + style + quality, scoped to branch diff | [pr-review-arch.md](pr-review-arch.md), [pr-review-style.md](pr-review-style.md), [pr-review-quality.md](pr-review-quality.md) |

## Default mode selection

- No mode specified → **Standard**
- "deep", "stale code", "safe to merge" → **Aggressive**
- "architecture", "layers", "coupling", "where does this belong" → **Architecture**
- "cleanup", "refactor", "simplify", "dead code" → **Cleanup**
- "frontend and backend", "contract", "schema drift", "route" → **Contract**
- "quick check", "pre-merge", "baseline" → **Baseline**
- "pr review", "pre-PR", called from check-pr-readiness → **PR Review** (three sequential passes)

## Constraints (all modes)

- Do not implement fixes. Report only.
- Do not elevate style-only comments into findings.
- Every finding needs file and line evidence.
- Scope review to changed files unless mode explicitly expands it.

## Repo references

- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- `.github/BOT_STYLE_GUIDE.md`
- `docs/style/python-style.md`
- `scripts/run_checks.py`, `scripts/checks/`
