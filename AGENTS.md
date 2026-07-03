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
- Skill authoring and localization guidance: `.ai/skills/manage-skill/SKILL.md`
- Supplemental Copilot-specific guidance: `.github/copilot-instructions.md`
  - `AGENTS.md` is the source of truth for durable repo instructions.
  - Read `.github/copilot-instructions.md` after `AGENTS.md` when Copilot/tool-specific legacy context is needed.
- For a readable current DB schema view, run `python -m scripts.data_ops.describe_db_schema` or `python -m scripts.data_ops.describe_db_schema --source live` instead of relying on a hand-maintained schema markdown mirror.

## Output style

- Apply a **balanced** style (see `docs/conventions/general-style.md`): prefer a touched file's existing local style, make consistency improvements only when they reduce ambiguity, and avoid broad style-only churn. Keep behavior unchanged unless asked.
- Do **not** do style-only rewrites unless explicitly requested.
- Explain any non-trivial style decision in your summary.
- For new code, apply the relevant language guide by default — `docs/conventions/python-style.md` (Python), `docs/conventions/frontend-style.md` (TypeScript/frontend).
- After each completed implementation phase and in final summaries, include:
  - `Developer verification`: exact UI route/tab/control, API endpoint and expected payload, report path, command output, or behavioral expectation a developer can inspect.
  - `Validation run`: tests and checks executed, or why validation was not run.
  - `Cleanup/robustness notes`: obsolete code removed, evidence-based cleanup candidates found in the touched scope, or `none found in touched scope`.
- Cleanup reporting is advisory by default. Do not broaden a feature branch with unrelated removals unless the obsolete path is directly created or exposed by the current change and validation proves removal is safe.

## Task surfaces

Skills are the repository's single task surface. (Repo-specific `.agent.md` personas were retired
2026-07-02 — their unique safety content moved into skills and `docs/architecture/architecture-conventions.md`.)

### Skills

Use a skill whenever the task matches one.

**Skills layout:** Canonical definitions live in folder-based files (`.ai/skills/<skill-name>/SKILL.md`). Reference files (mode-specific or domain-specific detail) live as flat `.md` files inside the same skill folder and are loaded on demand.

Do not reintroduce retired flat `.skill.md` shims, blank skill templates, or retired standalone skills without a fresh decision.

Current skill inventory:

| Skill | Purpose |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: deterministic gate + AI code/arch review + report |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract, PR review |
| `create-runtime-job/` | Scaffold a new runtime job against the shared runner (module + test + sentinel + schedule + inventory) |
| `db-migration/` | Schema migration lifecycle: create, validate, estimate risk, generate rollback |
| `expand-tests/` | Coverage growth and regression-test expansion |
| `finance-strategy/` | Financial terminology, strategy classification, market mechanics, and evaluation honesty |
| `help/` | Interactive discovery: list available skills and common prompts |
| `manage-skill/` | Create, improve, or refactor skills following the skills guide |
| `reference-doc/` | Reference docs and ADRs in `docs/reference/` |
| `update-documentation/` | Docs drift sync — rewrite stale prose, descriptions, and responsibilities |
| `validate-code/` | Deterministic validation: layer check, lint, type check, targeted tests |

## Routing guide

Default to the most specific matching skill; work without one when nothing matches.

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
| Add or scaffold a new runtime job | `create-runtime-job/` |
| Create a new skill | `manage-skill/` |
| Update or improve a skill | `manage-skill/` |
| Discover available skills and prompts | `help/` |
| Schema migration work or safety review | `db-migration/` |
| Broker adapters or live-trading safety review | `code-review/` (Aggressive mode) + the Live Trading Safety Guard in `docs/architecture/architecture-conventions.md` |
| Runtime job / scheduler work | `create-runtime-job/` for new jobs; `docs/reference/runtime-jobs.md` + `docs/runbooks/` for operating existing ones |
| Backtest methodology, walk-forward, evaluation honesty | `finance-strategy/` (Evaluation honesty) + `docs/reference/backtesting.md` |

## Shortcut workflows

These phrases are repo conventions for common tasks.

### `select skill:` (alias: `select bot:`)

- Treat this as a routing request before normal execution.
- Parse the text after the prefix as the task description.
- Return:
  1. recommended skill name (or "no skill — plain session")
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

**Suite names mirror the `tests/` directory tree** — the suite for a source area is its
source path (e.g. changed `src/trading/services/promotion/` → `run suite
src/trading/services/promotion`; changed `apps/paper_trading_web/backend/` →
`run suite apps/paper_trading_web`). Discover all valid names with `run suite --list`.
After editing files under a source area, run its matching suite before committing —
or use `run suite --changed` to auto-detect.

Command: `python -m scripts.checks.run_suite <suite> [extra pytest flags]`

Pass `--no-cov` for fast iteration without coverage overhead.

### `run checks`

- Run `python -m scripts.run_checks --profile quick`.
- Report pass/fail by step and include failing command details.

### `fix checks`

- Run `python -m scripts.fix_checks`.
- Use this only for deterministic, behavior-preserving cleanup such as Ruff safe fixes, formatting, and generated reference-doc asset sync.
- Afterward, run `python -m scripts.run_checks --profile quick` unless the user asked only for the fixer.

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

Follow `.ai/skills/check-pr-readiness/SKILL.md` — it owns the fail-fast step sequence
(deterministic gate → architecture → style → quality → docs check → report saved to
`local/pr_readiness_report.md`).

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
