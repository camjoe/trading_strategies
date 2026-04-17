# Reusable Skills Library

## Purpose

This folder is the repo's **primary reusable task surface**.

The goal is to keep generic capability in skills and reserve agents for the smaller set of cases that truly need repo-specific execution details.

## Skill-first model

Use a skill directly by default.

Keep or create an agent only when the task needs:

- exact repo paths or command entrypoints
- project-only safety rules
- project_manager workflow integration
- domain behavior too specific for the general skill

If a skill and an agent both exist for the same job, the default bias is:

1. use the skill
2. justify the agent
3. delete the agent if it adds no repo-specific execution value

## Layout

| Path | Purpose |
|---|---|
| `skills/portable/*.skill.md` | Reusable, directly usable general skills |
| `skills/templates/portable.skill.template.md` | Template for new portable skills |
| `skills/templates/local-overlay.agent.template.md` | Template for the rare repo-specific overlay agent that is still justified |

## Current skill pack

| Skill | Use directly? | Notes |
|---|---|---|
| `architecture-review.skill.md` | Yes | Default surface for structure/layering review |
| `code-review.skill.md` | Yes | Default surface for generic review/audit work |
| `deep-code-review.skill.md` | Yes | Default surface for broad simplification/staleness review |
| `docs-sync.skill.md` | Yes | Default surface for documentation drift work |
| `frontend-cleanup.skill.md` | Yes | Default surface for frontend-only cleanup |
| `python-cleanup.skill.md` | Yes | Default surface for Python cleanup |
| `python-stat-modeling.skill.md` | Yes | Default surface for general modeling/research tasks |
| `finance-strategy.skill.md` | Yes | Default surface for terminology/strategy explanation |
| `test-expansion.skill.md` | Yes | Default surface for generic testing work |
| `ui-api-contract.skill.md` | Usually | Escalate to `ui-api-steward.agent.md` only when repo-specific UI behavior matters |

## Agents that still remain

These agents still exist because they encode repo-specific execution behavior that the skills should not absorb:

| Agent | Repo-specific value |
|---|---|
| `task-runner.global.agent.md` | project_manager task workflow, branch/commit/PR automation |
| `backtesting-analyst.agent.md` | exact backtesting/reporting/UI paths and evaluation flows |
| `broker-live-safety.agent.md` | repo-specific live-trading safety rules |
| `db-migration-steward.agent.md` | repo-specific SQLite migration and backup rules |
| `trading-runtime.agent.md` | exact runtime job and operator flows |
| `ui-api-steward.agent.md` | exact `paper_trading_ui` contract paths and semantics |

## Authoring rules

### Portable skills should

1. stay generic enough to reuse in a similar repo
2. describe responsibilities, constraints, and expected outputs
3. list the facts that need localization later
4. avoid hardcoding repo-only paths unless shown as placeholders to replace

### Portable skills should not

1. assume this repo's file layout is universal
2. present repo-specific commands as if they exist everywhere
3. absorb project-only safety rules that belong in a dedicated overlay agent

## When to add a new skill vs agent

Add a new **skill** when the capability should be directly reusable in another project with only light localization.

Add a new **agent** only when the task depends on repo-specific execution behavior that would make the skill less reusable or more confusing.

## Workflows

### Bootstrap workflow for another repo

1. Copy `skills/portable/` into the new project as the starter skill pack.
2. Add a project architecture rules document.
3. Create repo-specific agents only for tasks the general skills cannot cover cleanly.
4. Document the remaining agent layer separately so users understand why it still exists.
