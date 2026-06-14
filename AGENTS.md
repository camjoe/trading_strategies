# Trading Strategies Workspace Guide

Purpose: define the repo-level guidance, routing rules, and shortcut workflows for coding agents working in this repository.

## Core rules

- Before editing any file under `trading/`, read `.github/BOT_ARCHITECTURE_CONVENTIONS.md` in full.
- Respect the layering and ownership rules there. Do not invert dependency direction such as `interfaces -> services -> repositories/domain -> database`.
- If a requested change would violate those conventions, stop and flag it before proceeding.

## Python environment

- Always run Python tools from the repo virtualenv:
  - `./.venv/bin/python`
  - `./.venv/bin/pytest`
  - `./.venv/bin/pip`
- Do not use system `python`, `python3`, or `pytest`.
- If `./.venv` is missing, stop and ask before proceeding.

## Working references

- Architecture boundaries: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style and formatting expectations: `.github/BOT_STYLE_GUIDE.md`
- Docs freshness policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Skill authoring and localization guidance: `.github/skills/README.md`
- For a readable current DB schema view, run `python -m scripts.data_ops.describe_db_schema` or `python -m scripts.data_ops.describe_db_schema --source live` instead of relying on a hand-maintained schema markdown mirror.

## Task surfaces

This repository uses two task surfaces:

### 1. Skills

Use a skill by default when the task is generic enough to be reusable.

**Skills layout:** Canonical definitions live in folder-based files (`.github/skills/<skill-name>/SKILL.md`). Thin flat shims may also exist at `.github/skills/<skill-name>.skill.md` for compatibility. If both exist, the folder-based `SKILL.md` is canonical.

Current skill inventory:

| Skill | Purpose |
|---|---|
| `architecture-review/` | Layering, dependency direction, and structure review |
| `code-cleanup/` | Backend, frontend, or mixed cleanup and refactor work |
| `code-review/` | Diff-based review plus deep audit mode for stale code and redundancy |
| `code-review-baseline/` | Lightweight pre-merge review — regressions and contract drift only |
| `code-review-aggressive/` | High-scrutiny review for safety-critical changes with zero-findings evidence |
| `docs-sync/` | Documentation drift detection and targeted sync |
| `finance-strategy/` | Financial terminology, strategy classification, and market mechanics |
| `python-stat-modeling/` | Time-series and finance/statistical modeling workflows |
| `reference-doc/` | Create or update a reference doc or ADR in `docs/reference/` |
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
| Lightweight quick diff check | `code-review-baseline/` |
| High-risk or safety-critical review (broker, DB, admin) | `code-review-aggressive/` |
| Whole-area simplification or stale-code audit | `code-review/` in deep mode |
| Create or update a reference doc or ADR | `reference-doc/` |
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

These phrases are repo conventions for common tasks.

### `select bot:`

- Treat this as a routing request before normal execution.
- Parse the text after `select bot:` as the task description.
- Return:
  1. recommended skill or agent name
  2. one-sentence reason
  3. whether to proceed with that surface now
- If no task text is provided, ask a short follow-up question.

### `code review`

- `code review`: review staged and unstaged changes against `HEAD`
- `code review: <branch>`: review the diff between the current branch and the given base branch
- `code review: <file-or-folder>`: review a specific area
- Follow `.github/skills/code-review/SKILL.md`.

### `deep code review`

- `deep code review`: review `trading/` and `paper_trading_ui/` together
- `deep code review: trading`: review `trading/`
- `deep code review: paper_trading_ui`: review `paper_trading_ui/`
- `deep code review: <file-or-folder>`: review a specific area with the same deep audit workflow
- Follow `.github/skills/code-review/SKILL.md` in deep-review mode.

### `sync docs` or `docs sync`

- Audit changed areas for documentation drift and apply targeted updates.
- Follow `.github/skills/docs-sync/SKILL.md`.
- After edits, run `python -m scripts.checks.readme_check`.

### `run suite`

Run a focused subset of tests by suite name or individual file path.

- `run suite trading/services` — run all trading services tests
- `run suite trading/services/market_data` — run tests for one service
- `run suite trading/services/market_data trading/services/promotion` — combine suites
- `run suite trading/services/market_data/test_features.py` — target a single file
- `run suite all` — run the full test suite
- `run suite --changed` — auto-detect suites from uncommitted changes
- `run suite --base main` — auto-detect suites from changes vs a branch (PR workflow)
- `run suite --list` — show all available suite names

Suite names mirror the `tests/` directory tree. After editing files under a
source area, run the matching suite to validate before committing:

| Changed source area | Run suite |
|---|---|
| `trading/services/accounting/` | `trading/services/accounting` |
| `trading/services/accounts/` | `trading/services/accounts` |
| `trading/services/admin/` | `trading/services/admin` |
| `trading/services/analysis/` | `trading/services/analysis` |
| `trading/services/auto_trading/` | `trading/services/auto_trading` |
| `trading/services/evaluation/` | `trading/services/evaluation` |
| `trading/services/ibkr_paper_monitor/` | `trading/services/ibkr_paper_monitor` |
| `trading/services/market_data/` | `trading/services/market_data` |
| `trading/services/pricing/` | `trading/services/pricing` |
| `trading/services/profiles/` | `trading/services/profiles` |
| `trading/services/promotion/` | `trading/services/promotion` |
| `trading/services/reporting/` | `trading/services/reporting` |
| `trading/services/runtime_settings/` | `trading/services` _(no dedicated subdir yet)_ |
| `trading/services/runtime_throttle/` | `trading/services` _(no dedicated subdir yet)_ |
| `trading/services/sleeves/` | `trading/services/sleeves` |
| `trading/services/` (multiple) | `trading/services` |
| `trading/interfaces/runtime/jobs/daily/` | `trading/interfaces/runtime/jobs/daily` |
| `trading/interfaces/runtime/jobs/governance/` | `trading/interfaces/runtime/jobs/governance` |
| `trading/interfaces/runtime/jobs/maintenance/` | `trading/interfaces/runtime/jobs/maintenance` |
| `trading/brokers/legacy/` | `trading/brokers/legacy` |
| `trading/backtesting/` | `trading/backtesting` |
| `trading/repositories/` | `trading/repositories` |
| `trading/interfaces/` | `trading/interfaces` |
| `paper_trading_ui/backend/` | `paper_trading_ui` |
| Any area | `all` |

Command: `python -m scripts.checks.run_suite <suite> [extra pytest flags]`

Pass `--no-cov` for fast iteration without coverage overhead.

### `run checks`

- Run `python -m scripts.run_checks --profile quick`.
- Report pass/fail by step and include failing command details.

### `run all checks`

- Run `python -m scripts.run_checks --profile ci`.
- Report pass/fail by step and include failing command details.

### `update documentation`

- Run `python -m scripts.checks.readme_check --repo-root . --max-age-days 90`.
- Report which README files need updates.
