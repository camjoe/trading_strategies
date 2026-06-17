# Reusable Skills Library

This folder is the repo's primary reusable task surface.

## Purpose

Define how this repository uses reusable skills vs repo-specific agents, and provide guardrails for maintaining both.

## Usage

1. Choose the closest matching skill folder and follow its `SKILL.md`.
2. Use a repo-specific agent only when the work depends on repo-only execution behavior.
3. To add or improve a skill, follow the authoring guide at `docs/Agent Skills.md`.

## Active layout

```
bots/skills/
├── <skill-name>/
│   ├── SKILL.md            ← canonical skill (loaded when skill triggers)
│   └── <reference>.md      ← reference files (loaded on demand by SKILL.md)
```

One folder per skill, lowercase hyphenated name. `SKILL.md` is the entry point. Additional `.md` files in the folder are reference documents loaded progressively as needed — they are not skills themselves.

## Current skill pack

| Skill folder | Covers |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: deterministic gate + AI code/arch review + report |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract, PR review |
| `create-skill/` | Authoring new skills following the skills guide |
| `db-migration/` | Schema migration lifecycle: create, validate, estimate risk, generate rollback |
| `expand-tests/` | Coverage growth and regression-test expansion |
| `finance-strategy/` | Financial terminology, strategy classification, and market mechanics |
| `reference-doc/` | Reference docs and ADRs in `docs/reference/` |
| `update-documentation/` | Docs drift sync and passive staleness check |
| `update-skill/` | Improving or refactoring existing skills |
| `validate-code/` | Deterministic validation: layer check, lint, type check, targeted tests |

### Reference files (inside skill folders, not skills themselves)

| File | Parent skill | Contains |
|---|---|---|
| `code-review/code-review.md` | `code-review/` | Standard, Baseline, and Deep diff review |
| `code-review/code-review-aggressive.md` | `code-review/` | High-scrutiny safety-critical review |
| `code-review/architecture-review.md` | `code-review/` | Layering and boundary review |
| `code-review/code-cleanup.md` | `code-review/` | Behavior-preserving refactor |
| `code-review/ui-api-contract.md` | `code-review/` | Frontend/backend contract alignment |
| `code-review/pr-review-arch.md` | `code-review/` | PR architecture constraints pass |
| `code-review/pr-review-style.md` | `code-review/` | PR style compliance pass |
| `code-review/pr-review-quality.md` | `code-review/` | PR quality standards pass |
| `db-migration/create-migration.md` | `db-migration/` | Write a new ColumnMigration entry |
| `db-migration/validate-migration.md` | `db-migration/` | Validate safety and correctness checklist |
| `db-migration/estimate-risk.md` | `db-migration/` | Blast radius, index needs, backtest impact |
| `db-migration/generate-rollback.md` | `db-migration/` | Rollback strategy for SQLite schema changes |
| `update-documentation/docs-sync.md` | `update-documentation/` | Active docs drift sync |
| `update-documentation/docs-check.md` | `update-documentation/` | Passive staleness check (advisory) |
| `validate-code/layer-check.md` | `validate-code/` | Layer boundary check |
| `validate-code/lint.md` | `validate-code/` | Ruff + eslint/tsc lint |
| `validate-code/type-check.md` | `validate-code/` | Mypy type check |
| `validate-code/tests.md` | `validate-code/` | Branch-targeted pytest + vitest |
| `reference-doc/reference-doc.md` | `reference-doc/` | Reference doc and ADR creation |

Retired from the active set:

- `code-review/code-review-baseline.md` (folded into `code-review.md` Baseline mode)
- `deep-code-review` (merged into `code-review` Aggressive mode)
- `frontend-cleanup` (merged into `code-review/code-cleanup.md`)
- `python-cleanup` (merged into `code-review/code-cleanup.md`)
- flat `.skill.md` shims (removed — not needed by Copilot CLI)
- `templates/` (removed — blank placeholders, not referenced by any workflow)

## Remaining repo-specific agents

These agents still exist because they encode repo-specific execution behavior that the skills should not absorb:

| Agent | Repo-specific value |
|---|---|
| `backtesting-analyst.agent.md` | Exact backtesting, reporting, and UI flows |
| `broker-live-safety.agent.md` | Live-trading safety rules |
| `db-migration-steward.agent.md` | SQLite migration and backup rules |
| `trading-runtime.agent.md` | Runtime job and operator flows |

Repo-specific agents live in `bots/agents/`.

## Authoring rules

Skills should:

1. stay reusable in a similar repo with light localization
2. have a gerund `name` and a third-person `description` with both WHAT and WHEN
3. keep `SKILL.md` under 500 lines — move details into reference files
4. use one-level-deep references only (no chaining)

Skills should not:

1. assume this repo's layout is universal
2. present repo-specific commands as if they exist everywhere
3. absorb project-only safety rules that belong in `AGENTS.md` or a repo-specific agent

## When to add a new skill vs agent

Add a new skill when the capability should be reusable outside this repo with only light localization.

Add a new agent only when the task depends on repo-specific execution behavior that would make the skill less reusable or more confusing.
