# Workspace Bot Standard

Purpose: define how bots operate in this repository without unnecessary process overhead.

## Agent Architecture

Agents in this project now use an additive three-layer model:

### Portable skills (`skills/portable/*.skill.md`)
Repo-local but reusable starter skills for bootstrapping a similar project before it has rich local agents.
These files are intentionally generic and should not hardcode `trading_strategies`-only paths or commands.
They are authoring assets, not replacements for `.github/agents/`.

### Global agents (`<name>.global.agent.md`)
Project-agnostic. Canonical source lives in `tools/project_manager/agents/` (the submodule).
Synced to `.github/agents/` via `python tools/project_manager/scripts/sync_agents.py`.
These agents carry no project-specific domain language and work with any project that uses
the project_manager submodule.

### Project-specific agents (`<name>.agent.md`)
Domain knowledge baked in. Live only in `.github/agents/`. Not synced to the submodule.

Local project-specific agents can specialize one or more portable skills with this repo's paths,
commands, architecture references, and safety rules.

### Portable skill inventory

| File | Purpose |
|------|---------|
| `skills/portable/architecture-review.skill.md` | Portable starter skill for layering and dependency-direction reviews |
| `skills/portable/code-review.skill.md` | Portable starter skill for changed-file audits and regression review |
| `skills/portable/deep-code-review.skill.md` | Portable starter skill for whole-area modernization, simplification, stale-code, and schema-relevance review |
| `skills/portable/docs-sync.skill.md` | Portable starter skill for documentation drift detection and targeted sync |
| `skills/portable/python-cleanup.skill.md` | Portable starter skill for Python readability and maintainability cleanup |
| `skills/portable/test-expansion.skill.md` | Portable starter skill for coverage growth and regression protection |
| `skills/portable/ui-api-contract.skill.md` | Portable starter skill for frontend/backend contract stewardship |

### Agent inventory

| File | Type | Purpose |
|------|------|---------|
| `code-review.global.agent.md` | 🌐 Global | Pre-commit audit: architecture, regressions, missing tests, dependency violations |
| `docs-sync.global.agent.md` | 🌐 Global | Keep README files, architecture notes, reference docs, and API docs in sync after code changes |
| `frontend-code-cleanup.global.agent.md` | 🌐 Global | Simplify TypeScript frontend code |
| `project-structure-steward.global.agent.md` | 🌐 Global | Enforce module boundaries and architecture |
| `python-code-cleanup.global.agent.md` | 🌐 Global | Refactor Python code for readability |
| `python-test-expansion.global.agent.md` | 🌐 Global | Add and strengthen Python tests |
| `task-runner.global.agent.md` | 🌐 Global | Task→branch→implement→commit→PR workflow |
| `backtesting-analyst.agent.md` | 🏠 Project | Backtesting, walk-forward, leaderboard, and evaluation-hygiene workflows |
| `deep-code-review.agent.md` | 🏠 Project | High-depth whole-area audit for simplification, stale code, redundancy, schema relevance, and architectural cleanup |
| `broker-live-safety.agent.md` | 🏠 Project | Broker adapter boundaries, live-trading safety guard, and reconciliation safety |
| `trading-runtime.agent.md` | 🏠 Project | Runtime jobs, scheduler operations, account lifecycle, and operational debugging |
| `ui-api-steward.agent.md` | 🏠 Project | Backend/frontend contract alignment for `paper_trading_ui` |
| `python-stat-modeling.agent.md` | 🏠 Project | Trading/finance statistical modeling |
| `trading-manager.agent.md` | 🏠 Project | Trading-domain orchestration |
| `finance-strategy.agent.md` | 🏠 Project | Financial terminology, strategy classification, signal interpretation, equity mechanics |
| `db-migration-steward.agent.md` | 🏠 Project | Schema migration safety, ColumnMigration audits, backup hygiene |

To sync global agents after pulling a submodule update:
```
python tools/project_manager/scripts/sync_agents.py
```

## Routing Guide

Use the most specific bot that matches the task's main risk.

| Task shape | Preferred bot | Why |
|------|------|---------|
| Architecture, layering, dependency direction | `project-structure-steward.global.agent.md` | Owns module-boundary review and placement rules |
| Pre-commit or pre-merge audit | `code-review.global.agent.md` | Reviews diffs and validation evidence instead of editing |
| Whole-area simplification, stale-code audit, consolidation, or schema relevance review | `deep-code-review.agent.md` | Performs a read-only deep audit of mature code areas beyond the current diff |
| README/reference drift | `docs-sync.global.agent.md` | Owns documentation freshness and targeted docs updates |
| Generic Python cleanup | `python-code-cleanup.global.agent.md` | Best default for behavior-preserving backend refactors |
| Generic test additions | `python-test-expansion.global.agent.md` | Focused on coverage and regression protection |
| Frontend-only cleanup | `frontend-code-cleanup.global.agent.md` | Best for TypeScript/UI readability without backend work |
| Cross-stack route/schema/UI contract work | `ui-api-steward.agent.md` | Specializes contract alignment across backend and frontend |
| Runtime jobs, schedulers, snapshots, account ops | `trading-runtime.agent.md` | Specializes operator-facing runtime flows and job boundaries |
| Broker adapters or live-trading safety | `broker-live-safety.agent.md` | Tightest guardrails for broker-facing and live-safety work |
| Backtest execution, walk-forward, leaderboard/report interpretation | `backtesting-analyst.agent.md` | Specializes evaluation workflow correctness and interpretation |
| Modeling, alpha research, feature engineering | `python-stat-modeling.agent.md` | Owns research and statistical modeling workflows |
| Financial concept explanation, strategy classification | `finance-strategy.agent.md` | Domain explanation without implementation work |
| Schema migration safety | `db-migration-steward.agent.md` | Owns SQLite migration review and backup hygiene |

## Overlap Boundaries

1. Prefer `backtesting-analyst.agent.md` for implementing or debugging existing evaluation flows; prefer `python-stat-modeling.agent.md` for designing or validating research pipelines.
2. Prefer `deep-code-review.agent.md` for broad, read-only modernization audits of `trading/`, `paper_trading_ui/`, or large subsystems; prefer `code-review.global.agent.md` for diff-based pre-commit review.
3. Prefer `ui-api-steward.agent.md` when both backend and frontend contracts are involved; prefer `frontend-code-cleanup.global.agent.md` when the change is purely frontend.
4. Prefer `trading-runtime.agent.md` for job runners, operator commands, snapshots, or health checks; prefer `python-code-cleanup.global.agent.md` for general backend cleanup outside runtime orchestration.
5. Prefer `broker-live-safety.agent.md` whenever a change touches broker configuration, factory logic, reconciliation, or live-trading protections.
6. Portable skills in `skills/portable/` are the authoring starting point for similar repos; `.github/agents/` remains the execution-ready layer for this repo.

## Important Clarification

Specialized bots are still present and usable in `.github/agents/`:

- `frontend-code-cleanup.global.agent.md`: simplify frontend code while preserving behavior and type safety.
- `docs-sync.global.agent.md`: keep README files, architecture notes, reference docs, and API docs in sync after code changes; detects drift, flags stale docs, writes targeted updates.
- `project-structure-steward.global.agent.md`: enforce module boundaries, dependency direction, and architecture consistency.
- `python-code-cleanup.global.agent.md`: refactor Python code for readability/maintainability without behavior changes; also handles mixed Python + frontend cleanup where cross-stack interface contracts need to stay stable.
- `backtesting-analyst.agent.md`: implement or interpret backtesting, walk-forward reporting, and leaderboard workflows with chronology and leakage safeguards.
- `deep-code-review.agent.md`: perform a high-depth, read-only audit for simplification, stale or superseded code, duplicated logic, schema relevance, and architectural cleanup opportunities.
- `broker-live-safety.agent.md`: protect broker adapter boundaries, live-trading guardrails, and reconciliation/config safety.
- `python-stat-modeling.agent.md`: build and evaluate trading-focused statistical modeling workflows.
- `python-test-expansion.global.agent.md`: add and strengthen tests, edge cases, and regression coverage.
- `task-runner.global.agent.md`: pick up a task from the project_manager DB, implement it on a feature branch, commit, push, and open a PR.
- `trading-runtime.agent.md`: work on runtime jobs, scheduler operations, account lifecycle flows, and operational debugging.
- `trading-manager.agent.md`: orchestrate bots for trading-domain tasks.
- `ui-api-steward.agent.md`: keep `paper_trading_ui` routes, schemas, services, and frontend consumers aligned as one contract.
- `code-review.global.agent.md`: audit changed files before commit or merge for architecture violations, regressions, missing tests, and dependency-direction issues.
- `finance-strategy.agent.md`: explain financial terminology, classify trading strategies, interpret market signals, and advise on equity mechanics and market microstructure.
- `db-migration-steward.agent.md`: validate schema changes and migration safety for the trading SQLite database; audit ColumnMigration additions, enforce additive-only rules, and ensure backup hygiene before destructive DB operations.

The `skills/` folder is additive. It provides portable starter prompts for similar repos, while `.github/agents/` remains the repo-specific execution layer.


## Canonical References

- Docs-impact and validation policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Script behavior and command flags: `scripts/README.md`
- Architecture boundaries: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Bot dependency/naming conventions: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style approach and formatting expectations: `.github/BOT_STYLE_GUIDE.md`
- Database migration system (hand-rolled SQLite, ColumnMigration pattern, backup flows): `docs/architecture/notes-db-migration-system.md`

## Core Operating Rules

1. Preserve behavior unless explicitly asked to change it.
2. Keep changes focused and avoid unrelated churn.
3. Follow architecture conventions in `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.
4. Keep docs synchronized with behavior changes.

## Conventions Ownership

1. `.github/BOT_ARCHITECTURE_CONVENTIONS.md` owns:
   - dependency direction
   - package/module ownership
   - naming conventions
   - abstraction/API consistency
   - cross-platform safety
2. `.github/BOT_STYLE_GUIDE.md` owns:
   - single balanced style approach
   - Python/frontend/docs styling expectations
   - style-only rewrite policy

## Safe Command Allowlist (For Fewer Approval Clicks)

Use this list for workspace-level "always allow" command approvals:

- `python -m scripts.run_checks --profile quick`
- `python -m scripts.run_checks --profile quick --with-frontend`
- `python -m scripts.run_checks --profile ci`
- `python -m scripts.run_checks --profile ci --skip-frontend`
- `python -m scripts.checks.readme_check`
- `python -m scripts.checks.readme_check --max-age-days 90`
- `python -m pytest`
- `python -m mypy paper_trading_ui/backend trading --python-version 3.14 --ignore-missing-imports --follow-imports=skip`
- `npm run lint` (from `paper_trading_ui/frontend`)
- `npm run typecheck` (from `paper_trading_ui/frontend`)
- `npm run test:coverage` (from `paper_trading_ui/frontend`)
- `python tools/project_manager/scripts/db_write.py list-items`
- `python tools/project_manager/scripts/db_write.py list-bots`
- `py tools/project_manager/scripts/commit_context`

Note: approval prompts are controlled by your VS Code/Copilot environment; this file documents the intended allowlist.

## Per-Bot Command Policies

Each bot has an explicit `## Permitted Shell Commands` section in its `.agent.md` file.
This table summarises the policy at a glance:

| Bot | Shell commands | Git access |
|-----|---------------|------------|
| Code Review (`*.global`) | `pytest`, `mypy`, `ruff check`; `npm run lint`, `npm run typecheck`, `npx vitest run`; `scripts.run_checks --profile quick` | ✅ Read-only (`diff`, `log`, `status`, `show`) |
| Docs Sync (`*.global`) | `scripts.checks.readme_check`, `scripts.run_checks --profile quick`; `scripts.reference_docs.check` (if available) | ❌ None |
| Frontend Code Cleanup (`*.global`) | `npm run lint`, `npm run typecheck`, `npm run test:coverage`, `npx vitest run` | ❌ None |
| Python Code Cleanup (`*.global`) | `pytest`, `mypy`, `ruff check`, `scripts.run_checks --profile quick`; npm commands for mixed-scope | ❌ None |
| Python Test Expansion (`*.global`) | `pytest`, `mypy`, `scripts.run_checks --profile quick` | ❌ None |
| Project Structure Steward (`*.global`) | `pytest`, `mypy`, `scripts.run_checks --profile quick\|ci` | ✅ Read-only (`diff`, `log`, `status`, `show`) |
| Task Runner (`*.global`) | `db_write.py`, `scripts.run_checks --profile quick`, `gh pr create` | ✅ Read+Write (`checkout -b`, `commit`, `push`; never `merge`/`rebase`/`reset`) |
| Python Statistical Modeling | `pytest`, `mypy`, `python -m trading.*`, `scripts.run_checks --profile quick` | ❌ None |
| Backtesting Analyst | `pytest -k "backtest or walk_forward or leaderboard"`, `mypy trading/backtesting/ paper_trading_ui/backend`, `scripts.run_checks --profile quick`; backtesting CLI `--help` commands | ❌ None |
| Deep Code Review | `git diff/status/log`; `scripts.run_checks --profile quick`; `pytest -k "trading or ui or backend or broker or backtest"`; `mypy trading paper_trading_ui/backend`; `ruff check trading paper_trading_ui/backend`; `npm run lint`; `npm run typecheck`; `npm run test:coverage` | ✅ Read-only (`diff`, `log`, `status`) |
| Broker Live Safety Steward | `pytest -k "broker or live_trading or reconciliation"`, `mypy trading/brokers/ trading/services/`, `scripts.run_checks --profile quick` | ❌ None |
| Trading Manager | `db_write.py`, `scripts/commit_context`, `scripts.run_checks --profile quick` | ✅ Read-only (`diff`, `log`, `status`) |
| Finance and Strategy Domain Bot | `scripts.run_checks --profile quick` (read-only health check only) | ❌ None |
| DB Migration Steward | `pytest` (db/migration/schema tests), `mypy trading/database/`, `scripts.run_checks --profile quick` | ❌ None |
| Trading Runtime Investigator | trading CLI `--help`; runtime job `--help`; `pytest -k "runtime or scheduler or snapshot or backup"`; `scripts.run_checks --profile quick` | ❌ None |
| UI API Steward | `scripts.run_checks --profile quick --with-frontend`; `pytest -k "ui or api or backend"`; `npm run lint`; `npm run typecheck`; `npm run test:coverage` | ❌ None |

**Git access tiers:**
- ❌ **None** — do not run any git commands
- ✅ **Read-only** — `git diff`, `git log`, `git status`, `git show` only; never `commit`, `push`, `merge`, `rebase`, `reset`, or `checkout`

When new bots are added, define their tier in the bot's `.agent.md`, update this table, and add a row to the routing guide above if the new bot overlaps an existing responsibility.
