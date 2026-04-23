# Trading Strategies Workspace Guide

Purpose: define the repo-level guidance, routing rules, and shortcut workflows for coding agents working in this repository.

## Core rules

- Before editing any file under `trading/`, read `.github/BOT_ARCHITECTURE_CONVENTIONS.md` in full.
- Respect the layering and ownership rules there. Do not invert dependency direction such as `interfaces -> services -> repositories/domain -> database`.
- If a requested change would violate those conventions, stop and flag it before proceeding.

## Working references

- Architecture boundaries: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style and formatting expectations: `.github/BOT_STYLE_GUIDE.md`
- Docs freshness policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Legacy Copilot-specific guidance: `.github/copilot-instructions.md`
- Skill authoring and localization guidance: `.github/skills/README.md`

## Task surfaces

This repository uses two task surfaces:

### 1. Skills

Use a skill by default when the task is generic enough to be reusable.

Current skill inventory:

| Skill | Purpose |
|---|---|
| `architecture-review/` | Layering, dependency direction, and structure review |
| `code-cleanup/` | Backend, frontend, or mixed cleanup and refactor work |
| `code-review/` | Diff-based review plus deep audit mode for stale code and redundancy |
| `docs-sync/` | Documentation drift detection and targeted sync |
| `finance-strategy/` | Financial terminology, strategy classification, and market mechanics |
| `python-stat-modeling/` | Time-series and finance/statistical modeling workflows |
| `test-expansion/` | Coverage growth and regression-test expansion |
| `ui-api-contract/` | Frontend/backend contract stewardship |

### 2. Repo-specific agents

Use an agent only when a skill is not enough and repo-specific execution value matters.

Current agent inventory:

| Agent | Why it still exists |
|---|---|
| `backtesting-analyst.agent.md` | Repo-specific backtesting and walk-forward flows tied to project paths, reports, and UI surfaces |
| `broker-live-safety.agent.md` | Repo-specific broker safety constraints and live-trading guardrails |
| `db-migration-steward.agent.md` | Repo-specific SQLite migration safety and backup hygiene |
| `trading-runtime.agent.md` | Repo-specific runtime jobs, scheduler flows, and operator-facing runtime behavior |

Keep an agent only if it adds one or more of:

- exact repo paths or command entrypoints
- project-only safety rules
- domain or workflow constraints too specific for a reusable skill
- operator workflow integration

## Routing guide

Default to the most specific matching skill. Escalate to a repo-specific agent only when repo-specific execution detail is materially important.

| Task shape | Preferred surface |
|---|---|
| Architecture, layering, dependency direction | `architecture-review/` |
| Pre-commit or pre-merge audit | `code-review/` |
| Whole-area simplification or stale-code audit | `code-review/` in deep mode |
| README, reference, or API drift | `docs-sync/` |
| Frontend-only cleanup in `paper_trading_ui/frontend` | `code-cleanup/` |
| Generic Python cleanup or refactor | `code-cleanup/` |
| Mixed backend and frontend cleanup | `code-cleanup/` |
| Generic test additions or edge-case coverage | `test-expansion/` |
| Financial concept or strategy explanation | `finance-strategy/` |
| Modeling, alpha research, feature engineering | `python-stat-modeling/` |
| Cross-stack route/schema/UI contract work | `ui-api-contract/` |
| Runtime jobs, schedulers, snapshots, account ops | `trading-runtime.agent.md` |
| Broker adapters or live-trading safety | `broker-live-safety.agent.md` |
| Backtest execution, walk-forward reporting, leaderboard behavior | `backtesting-analyst.agent.md` |
| Schema migration safety | `db-migration-steward.agent.md` |

Overlap rules:

1. If a skill and an agent overlap, use the skill unless the agent adds repo-specific execution value.
2. `backtesting-analyst.agent.md` remains useful for repo-specific evaluation, reporting, and walk-forward flows.

## Shortcut workflows

These phrases are accepted as repo conventions and should trigger the matching workflow.

### `select bot:`

- Treat this as a routing request before normal execution.
- Parse the text after `select bot:` as the task description.
- Return:
  1. recommended skill or agent name
  2. one-sentence reason
  3. whether to proceed with that surface now
- If no task text is provided, ask a short follow-up question.

### `code review`

- `code review`
  Review staged and unstaged changes against `HEAD`.
- `code review: <branch>`
  Review the diff between the current branch and the given base branch.
- `code review: <file-or-folder>`
  Review a specific area.
- Follow `.github/skills/code-review/SKILL.md`.

### `deep code review`

- `deep code review`
  Review `trading/` and `paper_trading_ui/` together.
- `deep code review: trading`
  Review `trading/`.
- `deep code review: paper_trading_ui`
  Review `paper_trading_ui/`.
- `deep code review: <file-or-folder>`
  Review a specific area with the same deep audit workflow.
- Follow `.github/skills/code-review/SKILL.md` in deep-review mode.

### `sync docs` or `docs sync`

- Audit changed areas for documentation drift and apply targeted updates.
- Follow `.github/skills/docs-sync/SKILL.md`.
- After edits, run `python -m scripts.checks.readme_check`.

### `run checks`

- Run `python -m scripts.run_checks --profile quick`.
- Report pass/fail by step and include failing command details.

### `run all checks`

- Run `python -m scripts.run_checks --profile ci`.
- Report pass/fail by step and include failing command details.

### `update documentation`

- Run `python -m scripts.checks.readme_check --repo-root . --max-age-days 90`.
- Report which README files need updates.

## Notes

- The archived predecessor to this file is `.github/AGENTS.legacy.md`.
- Retired flat Copilot-era skill files are archived under `.github/skills/legacy/`.
- Copilot-era details that are too tool-specific to keep as repo-global policy remain in `.github/copilot-instructions.md` for reference.
