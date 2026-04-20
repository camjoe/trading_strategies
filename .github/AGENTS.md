# Workspace Bot Standard

Purpose: define the repo's skill-first task surfaces and the smaller set of repo-specific agents that remain necessary.

## Core model

This repository uses two layers:

### 1. Portable skills (`skills/portable/*.skill.md`)

These are the **primary reusable task surface**.

Use a skill directly by default when the task is generic enough to be expressed without repo-specific commands, paths, or safety rules.

### 2. Repo-specific agents (`.github/agents/*.agent.md`)

These exist only when the skill alone is not enough.

Keep an agent only if it adds one or more of:

- exact repo paths or command entrypoints
- project-only safety rules
- domain or workflow constraints too specific for the reusable skill
- project_manager or operational workflow integration

## Current skill inventory

| Skill | Purpose |
|---|---|
| `architecture-review.skill.md` | Layering, dependency direction, and structure review |
| `code-review.skill.md` | Diff-based code review and regression audit |
| `deep-code-review.skill.md` | Whole-area simplification, stale-code, and redundancy review |
| `docs-sync.skill.md` | Documentation drift detection and targeted sync |
| `frontend-cleanup.skill.md` | Frontend-only readability and maintainability cleanup |
| `python-cleanup.skill.md` | Python-first cleanup and refactor work |
| `python-stat-modeling.skill.md` | Time-series and finance/statistical modeling workflows |
| `finance-strategy.skill.md` | Financial terminology, strategy classification, and market mechanics |
| `test-expansion.skill.md` | Coverage growth and regression-test expansion |
| `ui-api-contract.skill.md` | Frontend/backend contract stewardship |

## Current agent inventory

| Agent | Why it still exists |
|---|---|
| `task-runner.global.agent.md` | Repo-specific task workflow: project_manager task pickup, branch creation, commit, push, and PR |
| `backtesting-analyst.agent.md` | Repo-specific backtesting and walk-forward flows tied to project paths, reports, and UI surfaces |
| `broker-live-safety.agent.md` | Repo-specific broker safety constraints and live-trading guardrails |
| `db-migration-steward.agent.md` | Repo-specific SQLite migration safety and backup hygiene |
| `trading-runtime.agent.md` | Repo-specific runtime jobs, scheduler flows, and operator-facing runtime behavior |
| `ui-api-steward.agent.md` | Repo-specific `paper_trading_ui` route/schema/frontend contract behavior |

To sync the one active global agent after pulling a submodule update:

```bash
python tools/project_manager/scripts/sync_agents.py
```

## Routing guide

Use a **skill** unless the task falls into one of the repo-specific agent cases below.

| Task shape | Preferred surface | Why |
|---|---|---|
| Architecture, layering, dependency direction | `skills/portable/architecture-review.skill.md` | Reusable review pattern; no dedicated repo agent needed |
| Pre-commit or pre-merge audit | `skills/portable/code-review.skill.md` | Generic review capability is portable |
| Whole-area simplification or stale-code audit | `skills/portable/deep-code-review.skill.md` | Generic review capability is portable |
| README/reference/API drift | `skills/portable/docs-sync.skill.md` | Generic doc-sync capability is portable |
| Frontend-only cleanup | `skills/portable/frontend-cleanup.skill.md` | Generic frontend cleanup capability is portable |
| Generic Python cleanup | `skills/portable/python-cleanup.skill.md` | Generic Python cleanup capability is portable |
| Generic test additions | `skills/portable/test-expansion.skill.md` | Generic test-expansion capability is portable |
| Financial concept explanation | `skills/portable/finance-strategy.skill.md` | Generic domain explanation capability is portable |
| Modeling, alpha research, feature engineering | `skills/portable/python-stat-modeling.skill.md` | Generic modeling capability is portable |
| Cross-stack route/schema/UI contract work | `skills/portable/ui-api-contract.skill.md` | Start with the generic skill, move to the agent only if repo-specific UI behavior matters |
| Repo-specific `paper_trading_ui` contract/debug work | `ui-api-steward.agent.md` | Encodes exact repo paths, commands, and UI behavior |
| Runtime jobs, schedulers, snapshots, account ops | `trading-runtime.agent.md` | Encodes exact runtime entrypoints and operator flows |
| Broker adapters or live-trading safety | `broker-live-safety.agent.md` | Encodes hard repo-specific broker safety rules |
| Backtest execution, walk-forward reporting, leaderboard behavior | `backtesting-analyst.agent.md` | Encodes repo-specific evaluation/reporting surfaces |
| Schema migration safety | `db-migration-steward.agent.md` | Encodes repo-specific SQLite migration rules |
| project_manager task pickup through branch/PR | `task-runner.global.agent.md` | Encodes repo-specific workflow integration |

## Overlap rules

1. If a skill and an agent overlap, use the **skill** unless the agent adds repo-specific execution value.
2. `ui-api-steward.agent.md` remains because `paper_trading_ui` contract work depends on exact repo paths, services, commands, and payload semantics.
3. `backtesting-analyst.agent.md` remains because the repo's backtesting and reporting flows are more specific than the general modeling skill.
4. `task-runner.global.agent.md` remains because it integrates with this repo's project_manager workflow rather than representing a generic coding capability.

## Canonical references

- Architecture boundaries: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style and formatting expectations: `.github/BOT_STYLE_GUIDE.md`
- Docs freshness policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Script behavior and command flags: `tools/project_manager/scripts/README.md`
- Skill authoring and localization guidance: `skills/README.md`
