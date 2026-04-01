# Session Backup Rule

- Before the first write to `tools/project_manager/data/project_db.json` in any session — whether via `db_write.py` or a direct file edit — a backup must be created.
- When using `db_write.py`, the backup is automatic: it writes `db_backups/project_db_session_YYYY-MM-DD.json` once per calendar day before the first write.
- If editing `project_db.json` directly (not via `db_write.py`), manually copy the file to `tools/project_manager/db_backups/project_db_session_YYYY-MM-DD.json` first.
- No backup is needed for read-only operations.

# Backup Restore Rule

- To list available backups: `npm run restore:backup -- --list` (run from `tools/project_manager/`).
- To restore a specific backup: `npm run restore:backup -- <backup-file-name>` (run from `tools/project_manager/`).
- Only restore when `data/project_db.json` is missing, corrupted, or has been incorrectly modified.
- After a restore, verify the file is valid JSON before continuing.

# Architecture Guard

- Before editing any file under `trading/` (including subdirectories such as `trading/services/`, `trading/domain/`, `trading/repositories/`, etc.), read `.github/BOT_ARCHITECTURE_CONVENTIONS.md` in full.
- Respect the layering rules and package ownership map defined there. Do not invert the dependency direction (`interfaces → services → repositories/domain → database`).
- If a proposed change would violate a convention in that file, flag it to the user before proceeding.

# Commit Message Workflow

- When the user says they are ready to commit, asks for a commit message, or asks to summarize changes for commit, first run `py tools/project_manager/scripts/commit_context`.
- Default to `--git-scope project-manager` unless the user explicitly asks for the whole workspace repository or for both scopes.
- Use the script output as raw context: which tasks were newly archived, which files changed, and any documentation precheck warnings.
- Use newly archived items as the primary driver of commit message intent. If there are no newly archived items, fall back to the git changes.
- Write commit message options yourself based on that context — do not treat script output as the commit message.
- Include documentation precheck findings and explicitly note any warning where non-doc files changed without corresponding docs updates.
- Always present each commit message option in its own fenced code block so the user can copy it directly.
- Do not create a commit automatically unless the user explicitly requests it.

# Direct Commit Triggers

- If a user message is exactly `commit message git` (ignoring leading/trailing whitespace and case), bypass project-manager context generation and draft commit subject options from current uncommitted changes in this repository.
- For `commit message git`, summarize intent from staged + unstaged diffs against `HEAD`, and mention key changed files/areas that drove each option.
- If a user message is exactly `commit message task` (ignoring leading/trailing whitespace and case), run the standard commit-context workflow from the section above.
- For `commit message task`, default to `--git-scope project-manager` unless the user explicitly requests another scope.

# Run Task Shortcut

- If a user message starts with `run task` (ignoring leading/trailing whitespace and case), invoke the `Task Runner` agent.
- Accepted forms:
  - `run task` — list open items from project_manager DB and let the user pick one
  - `run task: <task-id>` — start immediately with the given task ID
- The Task Runner will create a branch `feature/pm-<task-id>-<slug>`, delegate to the best bot, run checks, commit (with user approval of the message), push, and open a PR.
- Always confirm bot selection and commit message with the user before proceeding.

# Sync Agents Shortcut

- If a user message is exactly `sync agents` (ignoring leading/trailing whitespace and case), run the global agent sync from the project_manager submodule.
- The default command is `python tools/project_manager/scripts/sync_agents.py` from the repo root.
- After the command finishes, report which agents were added, updated, or skipped.
- Run this after pulling submodule updates to get the latest global agents.

# Manager Shortcut

- If a user message starts with `manage` (ignoring leading/trailing whitespace and case), invoke the `Trading Manager` agent.
- Accepted forms: `manage`, `manage tasks`, `manage bots`, `manage: <focus>` (where focus is `assess tasks`, `delegate`, `bot status`, or `recommend improvements`).
- When no focus is specified, default to reading `tools/project_manager/data/project_db.json`, summarizing open tasks, and presenting a delegation plan.
- Always confirm with the user before invoking any delegated bot.

# Bot Routing Shortcut

- If a user message starts with `select bot:` then treat it as a routing request before normal execution.
- Parse the text after `select bot:` as the task description.
- If no task text is provided (for example the user only types `select bot:`), ask a short follow-up question for the target task/scope.
- Normalize matching by lowercasing the task text and stripping punctuation before heuristic checks.
- Run a quick bot-selection check and return:
	1. the recommended bot name,
	2. one-sentence reason,
	3. whether to proceed with that bot now.
- If the user confirms, invoke the selected specialized bot and continue.

Selection heuristics:

- `Code Review`: reviewing changed files for regressions, architecture violations, missing tests, dependency issues — before committing or merging.
- `Docs Sync`: updating README files, architecture notes, reference docs, API documentation, and inline docstrings after code changes — when docs may have drifted from behavior.
- `Frontend Code Cleanup`: frontend-only cleanup/refactor/readability in `paper_trading_ui/frontend`.
- `Python Code Cleanup`: Python cleanup/refactor/readability without behavior change, including mixed Python + frontend scope.
- `Python Test Expansion`: adding/improving tests and coverage depth.
- `Python Statistical Modeling`: trading/finance statistical modeling and time-series analysis.
- `Project Structure Steward`: architecture boundaries, module ownership, dependency direction.
- `Finance and Strategy Domain Bot`: explaining financial terminology, classifying trading strategies, interpreting signals, advising on equity mechanics and market microstructure — no implementation work.
- `DB Migration Steward`: validating schema changes and migration safety for the trading SQLite database; auditing `ColumnMigration` additions in `trading/database/db.py`, enforcing additive-only migration rules, checking column guards, and reviewing backup hygiene before destructive DB operations.
- `Docs Sync Bot`: keeping README files, architecture notes, reference docs, and API documentation in sync after code changes; detecting documentation drift, flagging stale sections, and writing targeted updates.

Suggested keyword cues for fast matching:

- `Code Review`: `review`, `code review`, `pre-commit`, `audit`, `regression`, `missing tests`, `dependency violation`, `arch violation`, `before commit`, `before merge`.
- `Docs Sync`: `docs sync`, `documentation sync`, `stale readme`, `readme update`, `api docs`, `doc drift`, `update docs`, `docs out of sync`, `documentation drift`, `sync docs`, `keep docs`, `docs after change`.
- `Frontend Code Cleanup`: `frontend`, `react`, `component`, `tsx`, `ui cleanup`, `vite`.
- `Python Code Cleanup`: `refactor`, `cleanup`, `python`, `readability`, `modularize`, `backend + frontend`, `cross-stack`, `api contract`, `end-to-end cleanup`.
- `Python Test Expansion`: `tests`, `coverage`, `pytest`, `edge case`, `regression test`.
- `Python Statistical Modeling`: `alpha`, `factor`, `timeseries`, `walk-forward`, `backtest`, `signal`.
- `Project Structure Steward`: `architecture`, `module boundaries`, `dependency direction`, `ownership`, `layering`.
- `Finance and Strategy Domain Bot`: `terminology`, `strategy classification`, `equity mechanics`, `signal interpretation`, `market microstructure`, `order types`, `short selling`, `dividends`, `corporate actions`, `momentum`, `mean-reversion`, `arbitrage`, `carry`, `event-driven`.
- `DB Migration Steward`: `migration`, `schema change`, `column migration`, `alter table`, `db schema`, `database migration`, `ColumnMigration`, `backup hygiene`, `destructive db`, `init_schema`, `sqlite migration`, `add column`.
- `Docs Sync Bot`: `stale docs`, `docs drift`, `readme out of date`, `sync docs`, `keep docs fresh`, `documentation out of sync`, `update readme`, `docs stale`, `missing documentation`.

- `Code Review`: `review`, `code review`, `pre-commit`, `audit`, `regression`, `missing tests`, `dependency violation`, `arch violation`, `before commit`, `before merge`.

1. If the task is about explaining or classifying a financial concept, strategy, signal, or equity mechanic without writing code, choose `Finance and Strategy Domain Bot`.
2. If the task is about reviewing, auditing, or checking code before commit/merge, choose `Code Review`.
3. If the task explicitly includes both frontend and Python/backend scope, choose `Python Code Cleanup` (it handles cross-stack routing internally).
4. If the task mentions tests/coverage as the primary objective, choose `Python Test Expansion`.
5. If the task mentions modeling/research/backtesting as the primary objective, choose `Python Statistical Modeling`.
6. If the task is architecture/module-boundary focused, choose `Project Structure Steward`.
7. If the task is about schema changes, database migrations, `ColumnMigration`, `ALTER TABLE`, `init_schema`, or backup hygiene for the trading DB, choose `DB Migration Steward`.
8. If the task is about stale or out-of-sync documentation, README drift, or keeping docs aligned with code, choose `Docs Sync Bot`.
9. Otherwise choose the most specific single-domain cleanup bot (`Frontend Code Cleanup` or `Python Code Cleanup`).

If multiple bots seem valid, default to `Python Code Cleanup` and state why.

# Code Review Shortcut

- If a user message starts with `code review` (ignoring leading/trailing whitespace and case), invoke the `Code Review Bot` agent.
- Accepted forms:
  - `code review` — review all staged + unstaged changes against HEAD
  - `code review: <branch>` — review the diff between the current branch and the given base branch
  - `code review: <file-or-folder>` — review a specific file or folder
- The bot reads changed files, runs linters/type-checkers, and reports findings by severity (🔴 HIGH, 🟡 MEDIUM, 🔵 LOW).
- It does not modify any files; it only audits and reports.

# Docs Sync Shortcut

- If a user message starts with `sync docs` or `docs sync` (ignoring leading/trailing whitespace and case), invoke the `Docs Sync Bot` agent.
- Accepted forms:
  - `sync docs` — audit all recently changed areas for documentation drift and apply targeted updates
  - `sync docs: <file-or-folder>` — restrict the sync to a specific file or module
  - `docs sync` — equivalent alias for `sync docs`
- The bot detects stale README files, outdated architecture notes, drifted API docs, and missing inline docstrings; it writes targeted updates without changing behavior.
- It runs `python -m scripts.checks.readme_check` after edits to validate freshness.

# Run Checks Shortcut

- If a user message is exactly `run checks` (ignoring leading/trailing whitespace and case), run the repository quick validation flow.
- The default command is `python -m scripts.run_checks --profile quick` from the repo root.
- After the command finishes, report pass/fail status by step and include failing command details when any step fails.
- If the user explicitly asks for broader parity with CI, use `python -m scripts.run_checks --profile ci` instead.

# Documentation Checks Shortcut

- If a user message is exactly `update documentation` (ignoring leading/trailing whitespace and case), run the repository documentation checks workflow.
- The default command is `python -m scripts.checks.readme_check --repo-root . --max-age-days 90` from the repo root.
- After the command finishes, report findings clearly and call out which README files need updates.

# Reference Docs Checks Shortcut

- If a user message is exactly `run reference doc checks` (ignoring leading/trailing whitespace and case), validate the Financial & Market, Software, and API reference workflows together.
- The default command is `python -m scripts.reference_docs.check` from the repo root.
- After the command finishes, report pass/fail status by section and call out any drift or missing descriptions/purposes.

# Sync Reference Docs Shortcut

- If a user message is exactly `sync reference docs` (ignoring leading/trailing whitespace and case), synchronize the markdown and Documentation page surfaces for Financial & Market, Software, and API references.
- The default command is `python -m scripts.reference_docs.sync_all` from the repo root.
- After the command finishes, report which sections were updated.

# Run All Checks Shortcut

- If a user message is exactly `run all checks` (ignoring leading/trailing whitespace and case), run the full validation flow for tests, audits, and documentation checks.
- The default command is `python -m scripts.run_checks --profile ci` from the repo root.
- After the command finishes, report pass/fail status by step and include failing command details when any step fails.

# Chat Help Shortcut

- If a user message is exactly `help` (ignoring leading/trailing whitespace), return a concise shortcut catalog before normal execution.
- The catalog should include each supported trigger phrase, what it does, and one example.
- Keep the catalog in sync with this file whenever shortcuts are added or modified.

Current shortcut catalog to show:

1. Trigger: `run task` / `run task: <task-id>`
	- Action: invokes the Task Runner agent — picks up a task from the project_manager DB, creates a feature branch, delegates to the best bot, commits (with approval), pushes, and opens a PR.
	- Example: `run task` or `run task: pm-nice-to-have-bots-code-review-bot`

2. Trigger: `sync agents`
	- Action: runs `python tools/project_manager/scripts/sync_agents.py` to copy updated global agents from the submodule into `.github/agents/`.
	- Example: `sync agents`

3. Trigger: `manage` / `manage tasks` / `manage: <focus>`
	- Action: invokes the Trading Manager agent — reads project_manager tasks, classifies them, presents a delegation plan, and recommends bot fleet improvements.
	- Example: `manage tasks` or `manage: recommend improvements`

4. Trigger: `select bot:`
	- Action: routes the task to the most appropriate specialized bot, shows recommendation/reason, and asks whether to proceed.
	- Example: `select bot: expand tests for trading reporting edge cases`

5. Trigger: `help`
	- Action: prints this shortcut catalog.
	- Example: `help`

6. Trigger: `commit message git`
	- Action: returns commit subject options based on current uncommitted git changes (staged + unstaged), without project-manager context.
	- Example: `commit message git`

7. Trigger: `commit message task`
	- Action: runs the project-manager commit-context workflow and returns task-aligned commit subject options.
	- Example: `commit message task`

8. Trigger: `run checks`
	- Action: runs `python -m scripts.run_checks --profile quick` and reports test/audit outcomes.
	- Example: `run checks`

9. Trigger: `update documentation`
	- Action: runs `python -m scripts.checks.readme_check --repo-root . --max-age-days 90` and reports documentation findings.
	- Example: `update documentation`

10. Trigger: `run reference doc checks`
	- Action: runs `python -m scripts.reference_docs.check` and reports Financial & Market, Software, and API reference sync status together.
	- Example: `run reference doc checks`

11. Trigger: `sync reference docs`
	- Action: synchronizes Finance, Software, and API markdown and UI surfaces from the canonical registries.
	- Example: `sync reference docs`

12. Trigger: `run all checks`
	- Action: runs `python -m scripts.run_checks --profile ci` for docs checks, audits, and test suites.
	- Example: `run all checks`

13. Trigger: `code review` / `code review: <branch-or-file>`
	- Action: invokes the Code Review Bot — audits staged/unstaged changes or a branch diff for architecture violations, missing tests, regressions, and dependency issues. Reports findings by severity without modifying files.
	- Example: `code review` or `code review: main`

14. Trigger: `sync docs` / `docs sync`
	- Action: invokes the Docs Sync Bot — detects documentation drift after code changes, updates stale README files, architecture notes, reference docs, and API documentation to match current behavior.
	- Example: `sync docs` or `docs sync`
