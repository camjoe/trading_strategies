# Trading Strategies Workspace Guide

Purpose: define the repo-level guidance, routing rules, and shortcut workflows for coding agents working in this repository.

## Core rules

- Before editing any file under `src/trading/`, read `docs/architecture/architecture-conventions.md` in full.
- Respect the layering and ownership rules there. Do not invert dependency direction such as `interfaces -> services -> repositories/domain -> database`.
- If a requested change would violate those conventions, stop and flag it before proceeding.

## Python environment

- Always run Python tools from the repo-local `.venv` virtual environment.
- Use the platform-appropriate interpreter and tool paths:
  - Windows: `.venv\Scripts\python.exe`, `.venv\Scripts\pytest.exe`, `.venv\Scripts\pip.exe`
  - POSIX: `./.venv/bin/python`, `./.venv/bin/pytest`, `./.venv/bin/pip`
- If a command example elsewhere in the repo uses a POSIX `.venv/bin/...` path, Windows agents should use the equivalent `.venv\Scripts\...` executable.
- Do not use system `python`, `python3`, or `pytest`.
- If `./.venv` is missing, stop and ask before proceeding.

## Working references

- Architecture boundaries: `docs/architecture/architecture-conventions.md`
- Style guides: `docs/conventions/general-style.md` (cross-cutting approach + docs/markdown), `docs/conventions/python-style.md` (Python), `docs/conventions/frontend-style.md` (TypeScript/frontend)
- Skill authoring and localization guidance: `.ai/skills/README.md`
- Supplemental Copilot-specific guidance: `.github/copilot-instructions.md`
  - `AGENTS.md` is the source of truth for durable repo instructions.
  - Read `.github/copilot-instructions.md` after `AGENTS.md` when Copilot/tool-specific legacy context is needed.
- For a readable current DB schema view, run `python -m scripts.data_ops.describe_db_schema` or `python -m scripts.data_ops.describe_db_schema --source live` instead of relying on a hand-maintained schema markdown mirror.

## Output style

- Apply a **balanced** style (see `docs/conventions/general-style.md`): prefer a touched file's existing local style, make consistency improvements only when they reduce ambiguity, and avoid broad style-only churn. Keep behavior unchanged unless asked.
- Do **not** do style-only rewrites unless explicitly requested.
- Explain any non-trivial style decision in your summary.
- For new code, apply the relevant language guide by default — `docs/conventions/python-style.md` (Python), `docs/conventions/frontend-style.md` (TypeScript/frontend).

## Task surfaces

This repository uses two task surfaces:

### 1. Skills

Use a skill by default when the task is generic enough to be reusable.

**Skills layout:** Canonical definitions live in folder-based files (`.ai/skills/<skill-name>/SKILL.md`). Reference files (mode-specific or domain-specific detail) live as flat `.md` files inside the same skill folder and are loaded on demand.

Current skill inventory:

| Skill | Purpose |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: deterministic gate + AI code/arch review + report |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract |
| `create-skill/` | Authoring new skills following the skills guide |
| `db-migration/` | Schema migration lifecycle: create, validate, estimate risk, generate rollback |
| `expand-tests/` | Coverage growth and regression-test expansion |
| `finance-strategy/` | Financial terminology, strategy classification, and market mechanics |
| `reference-doc/` | Reference docs and ADRs in `docs/reference/` |
| `update-documentation/` | Docs drift sync and passive staleness check |
| `update-skill/` | Improving or refactoring existing skills |
| `validate-code/` | Deterministic validation: layer check, lint, type check, targeted tests |

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
| Architecture, layering, dependency direction | `code-review/` (Architecture mode) |
| Pre-commit or pre-merge audit | `code-review/` (Standard mode) |
| Lightweight quick diff check | `code-review/` (Baseline mode) |
| High-risk or safety-critical review (broker, DB, admin) | `code-review/` (Aggressive mode) |
| Whole-area simplification or stale-code audit | `code-review/` (Cleanup mode) |
| Create or update a reference doc or ADR | `reference-doc/` |
| README, reference, or API drift | `update-documentation/` |
| Frontend-only cleanup in `apps/paper_trading_web/frontend` | `code-review/` (Cleanup mode) |
| Generic Python cleanup or refactor | `code-review/` (Cleanup mode) |
| Mixed backend and frontend cleanup | `code-review/` (Cleanup mode) |
| Generic test additions or edge-case coverage | `expand-tests/` |
| Financial concept or strategy explanation | `finance-strategy/` |
| Cross-stack route/schema/UI contract work | `code-review/` (Contract mode) |
| Pre-PR readiness check (any scope) | `check-pr-readiness/` |
| Run deterministic checks (lint, tests, layer) | `validate-code/` |
| Create a new skill | `create-skill/` |
| Update or improve a skill | `update-skill/` |
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
- Follow `.ai/skills/code-review/SKILL.md` (Standard mode).

### `deep code review`

- `deep code review`: review `src/trading/` and `apps/paper_trading_web/` together
- `deep code review: trading`: review `src/trading/`
- `deep code review: paper_trading_web`: review `apps/paper_trading_web/`
- `deep code review: <file-or-folder>`: review a specific area with the same deep audit workflow
- Follow `.ai/skills/code-review/SKILL.md` (Aggressive mode).

### `sync docs` or `docs sync`

- Audit changed areas for documentation drift and apply targeted updates.
- Follow `.ai/skills/update-documentation/SKILL.md`.
- After edits, run `python -m scripts.checks.readme_check`.

### `run suite`

Run a focused subset of tests by suite name or individual file path.

- `run suite src/trading/services` — run all trading services tests
- `run suite src/trading/services/market_data` — run tests for one service
- `run suite src/trading/services/market_data src/trading/services/promotion` — combine suites
- `run suite src/trading/services/market_data/test_features.py` — target a single file
- `run suite all` — run the full test suite
- `run suite --changed` — auto-detect suites from uncommitted changes
- `run suite --base main` — auto-detect suites from changes vs a branch (PR workflow)
- `run suite --list` — show all available suite names

Suite names mirror the `tests/` directory tree. After editing files under a
source area, run the matching suite to validate before committing:

| Changed source area | Run suite |
|---|---|
| `src/trading/services/accounting/` | `src/trading/services/accounting` |
| `src/trading/services/accounts/` | `src/trading/services/accounts` |
| `src/trading/services/admin/` | `src/trading/services/admin` |
| `src/trading/services/analysis/` | `src/trading/services/analysis` |
| `src/trading/services/auto_trading/` | `src/trading/services/auto_trading` |
| `src/trading/services/evaluation/` | `src/trading/services/evaluation` |
| `src/trading/services/ibkr_paper_monitor/` | `src/trading/services/ibkr_paper_monitor` |
| `src/trading/services/market_data/` | `src/trading/services/market_data` |
| `src/trading/services/pricing/` | `src/trading/services/pricing` |
| `src/trading/services/profiles/` | `src/trading/services/profiles` |
| `src/trading/services/promotion/` | `src/trading/services/promotion` |
| `src/trading/services/reporting/` | `src/trading/services/reporting` |
| `src/trading/services/runtime_settings/` | `src/trading/services` _(no dedicated subdir yet)_ |
| `src/trading/services/runtime_throttle/` | `src/trading/services` _(no dedicated subdir yet)_ |
| `src/trading/services/sleeves/` | `src/trading/services/sleeves` |
| `src/trading/services/` (multiple) | `src/trading/services` |
| `src/trading/interfaces/runtime/jobs/daily/` | `src/trading/interfaces/runtime/jobs/daily` |
| `src/trading/interfaces/runtime/jobs/governance/` | `src/trading/interfaces/runtime/jobs/governance` |
| `src/trading/interfaces/runtime/jobs/maintenance/` | `src/trading/interfaces/runtime/jobs/maintenance` |
| `src/infrastructure/brokers/legacy/` | `src/infrastructure/brokers/legacy` |
| `src/trading/backtesting/` | `src/trading/backtesting` |
| `src/trading/repositories/` | `src/trading/repositories` |
| `src/trading/interfaces/` | `src/trading/interfaces` |
| `apps/paper_trading_web/backend/` | `apps/paper_trading_web` |
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

### `pr ready`

Full pre-PR readiness workflow. Runs all deterministic checks (layer, lint, tests) and then AI-assisted review (architecture, style, quality), finishing with a saved PR readiness report.

- `pr ready` — full 6-step workflow vs `develop` (default base)
- `pr ready: <base>` — full 6-step workflow vs a custom base branch (e.g. `pr ready: main`)

Follow `.ai/skills/check-pr-readiness/SKILL.md`.

**Step sequence (fail-fast):**

| Step | Type | What runs |
|---|---|---|
| 1 | Deterministic | Layer boundary check + ruff lint + mypy + branch-targeted tests |
| 2 | AI | Architecture review — layer violations, dependency direction |
| 3 | AI | Style review — naming, docs, consistency beyond ruff |
| 4 | AI | Quality review — SRP, modularity, unnecessary patterns |
| 5 | AI | Docs check — README staleness (advisory, never blocks) |
| Report | AI | Saved to `local/pr_readiness_report.md` + printed |

**Individual step shortcuts** — run any step on its own:

| Shortcut | What it does |
|---|---|
| `pr tests` | Branch-targeted tests only (`--base develop`) |
| `pr tests: <base>` | Branch-targeted tests vs a custom base |
| `pr lint` | Layer check + ruff + mypy only |
| `pr code review` | AI style + quality review for branch diff vs develop |
| `pr code review: <base>` | AI style + quality review vs a custom base |
| `pr arch review` | AI architecture review for branch diff vs develop |
| `pr arch review: <base>` | AI architecture review vs a custom base |

**Deterministic-only command** (no AI, no tokens):

```
python -m scripts.checks.pr_ready
python -m scripts.checks.pr_ready --base main
python -m scripts.checks.pr_ready --no-cov          # faster, skips coverage
python -m scripts.checks.pr_ready --skip-tests      # layer + lint only
```

---

## Agent shortcuts

These phrases launch a **repo-specific agent** in a separate context window. Use them when you want to delegate a full task rather than ask in the current conversation. Each agent has exact repo paths, safety constraints, and permitted commands baked in.

### `migrate:` — DB Migration Steward

Validates schema changes and migration safety. Use for any `ColumnMigration` addition, column guard check, nullability change, or destructive data-op review.

- `migrate: add column <name> to <table>` — validate a proposed migration
- `migrate: review` — audit recent or uncommitted migration changes
- `migrate: backup check` — verify backup hygiene before a destructive op

Agent: `.ai/agents/db-migration-steward.agent.md`
Skills: `.ai/skills/db-migration/` (create, validate, estimate-risk, generate-rollback)

### `broker:` — Broker Live Safety Steward

Works on broker adapters, factory routing, and live-trading safety guards. Use when touching `src/infrastructure/brokers/`, `broker_type` routing, or any live-trading config flow.

- `broker: <description>` — implement or review broker adapter work
- `broker review` — review broker-facing changes in the current diff
- `broker: add <adapter>` — implement a new broker adapter safely

Agent: `.ai/agents/broker-live-safety.agent.md`

### `runtime:` — Trading Runtime Investigator

Works on paper-trading runtime jobs, scheduler flows, account lifecycle, and operational debugging. Use when touching `src/trading/interfaces/runtime/` or runtime CLI commands.

- `runtime: <description>` — implement or debug a runtime job or scheduler flow
- `runtime review` — review runtime-facing changes in the current diff
- `runtime: debug <job or symptom>` — investigate a runtime failure or unexpected behavior

Agent: `.ai/agents/trading-runtime.agent.md`

### `backtest:` — Backtesting Analyst

Implements and interprets backtesting, walk-forward analysis, persisted run reporting, and leaderboard comparisons. Use when touching `src/trading/backtesting/` or backtest-related UI surfaces.

- `backtest: <description>` — implement or extend a backtesting workflow
- `backtest review` — review backtesting changes in the current diff
- `backtest: explain <metric or result>` — interpret a backtest result or leaderboard output

Agent: `.ai/agents/backtesting-analyst.agent.md`

