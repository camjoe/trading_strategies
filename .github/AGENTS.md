# Workspace Bot Standard

Purpose: define how bots operate in this repository without unnecessary process overhead.

## Agent Architecture

Agents in this project follow a two-tier model:

### Global agents (`<name>.global.agent.md`)
Project-agnostic. Canonical source lives in `tools/project_manager/agents/` (the submodule).
Synced to `.github/agents/` via `python tools/project_manager/scripts/sync_agents.py`.
These agents carry no project-specific domain language and work with any project that uses
the project_manager submodule.

### Project-specific agents (`<name>.agent.md`)
Domain knowledge baked in. Live only in `.github/agents/`. Not synced to the submodule.

### Agent inventory

| File | Type | Purpose |
|------|------|---------|
| `code-review.global.agent.md` | 🌐 Global | Pre-commit audit: architecture, regressions, missing tests, dependency violations |
| `frontend-code-cleanup.global.agent.md` | 🌐 Global | Simplify TypeScript frontend code |
| `project-structure-steward.global.agent.md` | 🌐 Global | Enforce module boundaries and architecture |
| `python-code-cleanup.global.agent.md` | 🌐 Global | Refactor Python code for readability |
| `python-test-expansion.global.agent.md` | 🌐 Global | Add and strengthen Python tests |
| `task-runner.global.agent.md` | 🌐 Global | Task→branch→implement→commit→PR workflow |
| `python-stat-modeling.agent.md` | 🏠 Project | Trading/finance statistical modeling |
| `trading-manager.agent.md` | 🏠 Project | Trading-domain orchestration |
| `finance-strategy.agent.md` | 🏠 Project | Financial terminology, strategy classification, signal interpretation, equity mechanics |
| `db-migration-steward.agent.md` | 🏠 Project | Schema migration safety, ColumnMigration audits, backup hygiene |

To sync global agents after pulling a submodule update:
```
python tools/project_manager/scripts/sync_agents.py
```

## Important Clarification

Specialized bots are still present and usable in `.github/agents/`:

- `frontend-code-cleanup.global.agent.md`: simplify frontend code while preserving behavior and type safety.
- `project-structure-steward.global.agent.md`: enforce module boundaries, dependency direction, and architecture consistency.
- `python-code-cleanup.global.agent.md`: refactor Python code for readability/maintainability without behavior changes; also handles mixed Python + frontend cleanup where cross-stack interface contracts need to stay stable.
- `python-stat-modeling.agent.md`: build and evaluate trading-focused statistical modeling workflows.
- `python-test-expansion.global.agent.md`: add and strengthen tests, edge cases, and regression coverage.
- `task-runner.global.agent.md`: pick up a task from the project_manager DB, implement it on a feature branch, commit, push, and open a PR.
- `trading-manager.agent.md`: orchestrate bots for trading-domain tasks.
- `code-review.global.agent.md`: audit changed files before commit or merge for architecture violations, regressions, missing tests, and dependency-direction issues.
- `finance-strategy.agent.md`: explain financial terminology, classify trading strategies, interpret market signals, and advise on equity mechanics and market microstructure.
- `db-migration-steward.agent.md`: validate schema changes and migration safety for the trading SQLite database; audit ColumnMigration additions, enforce additive-only rules, and ensure backup hygiene before destructive DB operations.

This file provides shared baseline rules; it does not replace or remove those agents.


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
- `python tools/project_manager/scripts/generate_commit_context.py`

Note: approval prompts are controlled by your VS Code/Copilot environment; this file documents the intended allowlist.

## Per-Bot Command Policies

Each bot has an explicit `## Permitted Shell Commands` section in its `.agent.md` file.
This table summarises the policy at a glance:

| Bot | Shell commands | Git access |
|-----|---------------|------------|
| Code Review (`*.global`) | `pytest`, `mypy`, `ruff check`; `npm run lint`, `npm run typecheck`, `npx vitest run`; `scripts.run_checks --profile quick` | ✅ Read-only (`diff`, `log`, `status`, `show`) |
| Frontend Code Cleanup (`*.global`) | `npm run lint`, `npm run typecheck`, `npm run test:coverage`, `npx vitest run` | ❌ None |
| Python Code Cleanup (`*.global`) | `pytest`, `mypy`, `ruff check`, `scripts.run_checks --profile quick`; npm commands for mixed-scope | ❌ None |
| Python Test Expansion (`*.global`) | `pytest`, `mypy`, `scripts.run_checks --profile quick` | ❌ None |
| Project Structure Steward (`*.global`) | `pytest`, `mypy`, `scripts.run_checks --profile quick\|ci` | ✅ Read-only (`diff`, `log`, `status`, `show`) |
| Task Runner (`*.global`) | `db_write.py`, `scripts.run_checks --profile quick`, `gh pr create` | ✅ Read+Write (`checkout -b`, `commit`, `push`; never `merge`/`rebase`/`reset`) |
| Python Statistical Modeling | `pytest`, `mypy`, `python -m trading.*`, `scripts.run_checks --profile quick` | ❌ None |
| Trading Manager | `db_write.py`, `generate_commit_context.py`, `scripts.run_checks --profile quick` | ✅ Read-only (`diff`, `log`, `status`) |
| Finance and Strategy Domain Bot | `scripts.run_checks --profile quick` (read-only health check only) | ❌ None |
| DB Migration Steward | `pytest` (db/migration/schema tests), `mypy trading/database/`, `scripts.run_checks --profile quick` | ❌ None |

**Git access tiers:**
- ❌ **None** — do not run any git commands
- ✅ **Read-only** — `git diff`, `git log`, `git status`, `git show` only; never `commit`, `push`, `merge`, `rebase`, `reset`, or `checkout`

When new bots are added, define their tier in the bot's `.agent.md` and update this table.

