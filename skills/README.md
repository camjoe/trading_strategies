# Reusable Skills Library

This folder adds a portable skill layer on top of the existing repo-local agents in `.github/agents/`.

The rollout is intentionally additive:

- `skills/portable/` contains reusable starter skills for similar Python + TypeScript trading projects.
- `skills/templates/` contains authoring templates for new portable skills and local overlays.
- `.github/agents/` remains the home for `trading_strategies`-specific overlays with exact paths, commands, and safety rules.

## Purpose

Provide a reusable starter-skill library for similar projects while keeping `trading_strategies`-specific behavior in local overlay agents.

## Why both layers exist

Portable skills are useful when standing up a similar project quickly, before that project has rich local agent definitions.

Local overlays are useful when a skill needs repo-specific details such as:

- concrete paths like `trading/` or `paper_trading_ui/`
- architecture rules from `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- operational commands from this repo's scripts and CLIs
- safety constraints like live-trading protections

## Layout

| Path | Purpose |
|---|---|
| `skills/portable/*.skill.md` | Repo-agnostic starter skills |
| `skills/templates/portable.skill.template.md` | Template for new portable skills |
| `skills/templates/local-overlay.agent.template.md` | Template for new project-specific overlays |
| `.github/agents/*.agent.md` | `trading_strategies` local overlays and existing agents |

## Authoring rules

### Portable skills

Portable skills should:

1. stay generic enough to reuse in a similar repo
2. describe responsibilities, constraints, and expected outputs
3. list the kinds of local facts that must be filled in later
4. avoid hardcoding repo-only paths unless shown as examples to replace

Portable skills should not:

1. assume this repo's file layout is universal
2. reference this repo's exact commands as if they exist everywhere
3. embed private or environment-specific assumptions

### Local overlays

Local overlays should:

1. reference exact repo paths and command entrypoints
2. point to this repo's architecture and safety docs
3. tighten constraints where this project needs extra guardrails
4. stay focused on one responsibility so routing stays clear

## Workflows

### Bootstrap workflow for a similar project

1. Copy the files in `skills/portable/` into the new project as the starter skill pack.
2. Add a project architecture rules document for dependency direction, ownership, and naming.
3. Create a local agent folder such as `.github/agents/`.
4. Specialize the portable skills into local overlays by filling in:
   - repo paths
   - shell commands
   - validation commands
   - domain and safety constraints
5. Add a registry file similar to `.github/AGENTS.md` so contributors can see what is portable vs local.

## Global environment options

This repo keeps the portable skills in version control first. If you want cross-project reuse, choose one of these patterns:

### Option A: Repo-local source of truth

Keep `skills/portable/` here and copy the files into new projects when needed.

### Option B: Shared personal or team library

Mirror `skills/portable/` into a global directory or shared repository and treat this repo copy as either:

- the canonical source, or
- a synced consumer copy

If your assistant runtime supports a global skills folder, place unchanged copies of the portable files there and keep local overlays inside each target repo.

## Current starter pack

| Portable skill | Purpose | Suggested local overlay in this repo |
|---|---|---|
| `architecture-review.skill.md` | Layering and dependency checks | existing `project-structure-steward.global.agent.md` plus local architecture rules |
| `code-review.skill.md` | Regression and changed-file audit | existing `code-review.global.agent.md` |
| `docs-sync.skill.md` | Documentation drift detection | existing `docs-sync.global.agent.md` |
| `python-cleanup.skill.md` | Backend cleanup and refactor guidance | existing `python-code-cleanup.global.agent.md` |
| `test-expansion.skill.md` | Coverage and regression-test expansion | existing `python-test-expansion.global.agent.md` |
| `ui-api-contract.skill.md` | Backend/frontend contract stewardship | `ui-api-steward.agent.md` |

## Routing and overlap

For day-to-day bot selection, use `.github/AGENTS.md` as the source of truth. That file owns:

- the routing matrix for choosing the most specific bot
- overlap boundaries between similar bots
- the execution-ready inventory for this repository

This `skills/README.md` focuses on portable-vs-local setup, bootstrap guidance, and authoring rules.

## How to decide whether to add a new portable skill or local overlay

Add a new portable skill when the capability can be reused in another repository with only light localization.

Add a new local overlay when the capability depends on:

- exact repo paths
- exact commands
- project-only safety rules
- domain assumptions that would not transfer cleanly

## Initial local overlays added for trading_strategies

- `backtesting-analyst.agent.md`
- `broker-live-safety.agent.md`
- `trading-runtime.agent.md`
- `ui-api-steward.agent.md`

These are additive. They do not replace the existing global or project-specific agents already in `.github/agents/`.
