# Reusable Skills Library

This folder is the repo's primary reusable task surface.

## Purpose

Define how this repository uses reusable skills vs repo-specific agents, and provide guardrails for maintaining both.

## Usage

1. Choose the closest matching skill folder and follow its `SKILL.md`.
2. Use a repo-specific agent only when the work depends on repo-only execution behavior.
3. Keep top-level `.skill.md` files as compatibility shims only; treat folder `SKILL.md` files as canonical.

## Active layout

Use folder-based skills with a `SKILL.md` file:

| Path | Purpose |
|---|---|
| `.github/skills/<skill-name>/SKILL.md` | Active Codex-style skill definition |
| `.github/skills/<skill-name>.skill.md` | Thin Copilot-facing compatibility shim pointing at the canonical skill |
| `.github/skills/templates/portable.skill.template.md` | Template for drafting a portable skill |
| `.github/skills/templates/local-overlay.agent.template.md` | Template for the rare repo-specific overlay agent |

The active convention is one folder per skill using lowercase hyphenated names. Flat `.skill.md` files at the top of `.github/skills/` are compatibility shims, not the canonical source of truth.

## Skill-first model

Use a skill directly by default.

Keep or create an agent only when the task needs:

- exact repo paths or command entrypoints
- project-only safety rules
- operator workflow integration
- domain behavior too specific for the reusable skill

If a skill and an agent both exist for the same job:

1. use the skill first
2. justify the agent
3. remove the agent if it no longer adds repo-specific execution value

## Current skill pack

| Skill folder | Notes |
|---|---|
| `architecture-review/` | Default surface for structure and layering review |
| `code-cleanup/` | Default surface for backend, frontend, or mixed cleanup work |
| `code-review/` | Default surface for generic review work and deep audits |
| `code-review-baseline/` | Lightweight review variant — regressions and contract drift only; use for quick pre-merge checks |
| `code-review-aggressive/` | High-scrutiny review variant — safety-critical changes, explicit zero-findings evidence required |
| `docs-sync/` | Default surface for documentation drift work |
| `finance-strategy/` | Default surface for terminology and strategy explanation |
| `python-stat-modeling/` | Default surface for modeling and research tasks |
| `reference-doc/` | Default surface for creating or updating reference docs and ADRs in `docs/reference/` |
| `test-expansion/` | Default surface for generic testing work |
| `ui-api-contract/` | Default surface for frontend/backend contract work |

Retired from the active set:

- `deep-code-review` (merged into `code-review` deep mode)
- `frontend-cleanup` (merged into `code-cleanup`)
- `python-cleanup` (merged into `code-cleanup`)

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
2. describe responsibilities, constraints, workflow, and expected output
3. point to repo references only when those references materially improve execution
4. stay concise and avoid turning `SKILL.md` into general documentation

Skills should not:

1. assume this repo's layout is universal
2. present repo-specific commands as if they exist everywhere
3. absorb project-only safety rules that belong in `AGENTS.md` or a repo-specific agent

## When to add a new skill vs agent

Add a new skill when the capability should be reusable outside this repo with only light localization.

Add a new agent only when the task depends on repo-specific execution behavior that would make the skill less reusable or more confusing.
