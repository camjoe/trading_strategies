# Copilot Workspace Guidance

This repository uses `AGENTS.md` at the repo root as the primary shared guidance file.

## Canonical guidance files

- Primary repo guidance: `AGENTS.md`
- Architecture rules: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style guidance: `.github/BOT_STYLE_GUIDE.md`
- Docs freshness policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Skills overview: `.github/skills/README.md`

## Architecture guard

- Before editing files under `trading/`, read `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.
- Respect the dependency direction `interfaces -> services -> repositories/domain -> database`.
- If a requested change would violate those conventions, flag it before proceeding.

## Skills layout

The canonical skill definitions live in folder-based files:

- `.github/skills/<skill-name>/SKILL.md`

Thin flat compatibility shims may also exist at:

- `.github/skills/<skill-name>.skill.md`

If both exist, treat the folder-based `SKILL.md` as canonical and the flat `.skill.md` file as a Copilot-facing compatibility wrapper.

## Active skills

- `architecture-review`
- `code-cleanup`
- `code-review`
- `docs-sync`
- `finance-strategy`
- `python-stat-modeling`
- `test-expansion`
- `ui-api-contract`

## Active repo-specific agents

- `backtesting-analyst.agent.md`
- `broker-live-safety.agent.md`
- `db-migration-steward.agent.md`
- `trading-runtime.agent.md`

Use a skill by default. Use an agent only when the task depends on repo-specific execution rules, operational safety constraints, or workflow details that should not be absorbed into a portable skill.

## Routing shorthand

- Architecture or layering review -> `architecture-review`
- Cleanup or refactor work -> `code-cleanup`
- Review or audit work -> `code-review`
- Broad stale-code or simplification audit -> `code-review` in deep mode
- Documentation drift -> `docs-sync`
- Finance or strategy explanation -> `finance-strategy`
- Modeling or time-series methodology -> `python-stat-modeling`
- Test additions or coverage work -> `test-expansion`
- Frontend/backend contract work -> `ui-api-contract`
- Backtesting or walk-forward repo workflows -> `backtesting-analyst.agent.md`
- Runtime jobs, schedulers, snapshots, or operator flows -> `trading-runtime.agent.md`
- Broker adapters or live-trading safety -> `broker-live-safety.agent.md`
- Database migration safety -> `db-migration-steward.agent.md`

## Shortcut phrases

- `select bot:` -> route to the most appropriate skill or agent
- `code review` -> use `.github/skills/code-review/SKILL.md`
- `deep code review` -> use `.github/skills/code-review/SKILL.md` in deep-review mode
- `sync docs` or `docs sync` -> use `.github/skills/docs-sync/SKILL.md`
- `run checks` -> `python -m scripts.run_checks --profile quick`
- `run all checks` -> `python -m scripts.run_checks --profile ci`
- `update documentation` -> `python -m scripts.checks.readme_check --repo-root . --max-age-days 90`
