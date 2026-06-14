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
.github/skills/
├── <skill-name>/
│   ├── SKILL.md            ← canonical skill (loaded when skill triggers)
│   └── <reference>.md      ← reference files (loaded on demand by SKILL.md)
└── templates/              ← authoring templates
```

One folder per skill, lowercase hyphenated name. `SKILL.md` is the entry point. Additional `.md` files in the folder are reference documents loaded progressively as needed — they are not skills themselves.

## Current skill pack

| Skill folder | Covers |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: deterministic gate + AI code/arch review + report |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract |
| `create-memory/` | Reference docs and ADRs in `docs/reference/` |
| `create-skill/` | Authoring new skills following the skills guide |
| `finance-strategy/` | Financial terminology, strategy classification, and market mechanics |
| `python-stat-modeling/` | Time-series and finance/statistical modeling workflows |
| `test-expansion/` | Coverage growth and regression-test expansion |
| `update-documentation/` | Docs drift sync and reference doc / ADR creation |
| `update-skill/` | Improving or refactoring existing skills |
| `validate-code/` | Deterministic validation: layer check, lint, type check, targeted tests |

### Reference files (inside skill folders, not skills themselves)

| File | Parent skill | Contains |
|---|---|---|
| `code-review/code-review.md` | `code-review/` | Standard diff review |
| `code-review/code-review-baseline.md` | `code-review/` | Lightweight pre-merge review |
| `code-review/code-review-aggressive.md` | `code-review/` | High-scrutiny safety-critical review |
| `code-review/architecture-review.md` | `code-review/` | Layering and boundary review |
| `code-review/code-cleanup.md` | `code-review/` | Behavior-preserving refactor |
| `code-review/ui-api-contract.md` | `code-review/` | Frontend/backend contract alignment |
| `update-documentation/docs-sync.md` | `update-documentation/` | Docs drift detection and sync |
| `update-documentation/reference-doc.md` | `update-documentation/` | Reference doc and ADR creation |
| `create-memory/reference-doc.md` | `create-memory/` | Reference doc and ADR creation |

Retired from the active set:

- `deep-code-review` (merged into `code-review` Aggressive mode)
- `frontend-cleanup` (merged into `code-review/code-cleanup.md`)
- `python-cleanup` (merged into `code-review/code-cleanup.md`)
- flat `.skill.md` shims (removed — not needed by Copilot CLI)

## Remaining repo-specific agents

These agents still exist because they encode repo-specific execution behavior that the skills should not absorb:

| Agent | Repo-specific value |
|---|---|
| `backtesting-analyst.agent.md` | Exact backtesting, reporting, and UI flows |
| `broker-live-safety.agent.md` | Live-trading safety rules |
| `db-migration-steward.agent.md` | SQLite migration and backup rules |
| `trading-runtime.agent.md` | Runtime job and operator flows |

Repo-specific agents live in `.github/agents/`.

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
