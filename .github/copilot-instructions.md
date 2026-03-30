# Architecture Guard

- Before editing any file under `trading/` (including subdirectories such as `trading/services/`, `trading/domain/`, `trading/repositories/`, etc.), read `.github/BOT_ARCHITECTURE_CONVENTIONS.md` in full.
- Respect the layering rules and package ownership map defined there. Do not invert the dependency direction (`interfaces → services → repositories/domain → database`).
- If a proposed change would violate a convention in that file, flag it to the user before proceeding.

# Commit Message Workflow

- When the user says they are ready to commit, asks for a commit message, or asks to summarize changes for commit, first run `python .\tools\project_manager\scripts\generate_commit_context.py`.
- Default to `--git-scope project-manager` unless the user explicitly asks for the whole workspace repository or for both scopes.
- Use newly archived items from `tools/project_manager/data/project_db.json` as the primary source for commit-message intent when present.
- If there are no newly archived items, fall back to current git changes since `HEAD`.
- Include documentation precheck findings from script output, and explicitly note any warning where non-doc files changed without corresponding docs updates.
- Return a short set of commit subject options and explain briefly which archived items or changed areas they came from.
- Always present each commit message option in its own fenced code block so the user can copy it directly.
- Do not create a commit automatically unless the user explicitly requests it.

# Direct Commit Triggers

- If a user message is exactly `commit message git` (ignoring leading/trailing whitespace and case), bypass project-manager context generation and draft commit subject options from current uncommitted changes in this repository.
- For `commit message git`, summarize intent from staged + unstaged diffs against `HEAD`, and mention key changed files/areas that drove each option.
- If a user message is exactly `commit message task` (ignoring leading/trailing whitespace and case), run the standard commit-context workflow from the section above.
- For `commit message task`, default to `--git-scope project-manager` unless the user explicitly requests another scope.

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

- `Frontend Code Cleanup`: frontend-only cleanup/refactor/readability in `paper_trading_ui/frontend`.
- `Python Code Cleanup`: Python cleanup/refactor/readability without behavior change.
- `Python Test Expansion`: adding/improving tests and coverage depth.
- `Python Statistical Modeling`: trading/finance statistical modeling and time-series analysis.
- `Project Structure Steward`: architecture boundaries, module ownership, dependency direction.
- `Cross-Stack Cleanup Coordinator`: mixed Python + frontend scope or cross-layer cleanup.

Suggested keyword cues for fast matching:

- `Frontend Code Cleanup`: `frontend`, `react`, `component`, `tsx`, `ui cleanup`, `vite`.
- `Python Code Cleanup`: `refactor`, `cleanup`, `python`, `readability`, `modularize`.
- `Python Test Expansion`: `tests`, `coverage`, `pytest`, `edge case`, `regression test`.
- `Python Statistical Modeling`: `alpha`, `factor`, `timeseries`, `walk-forward`, `backtest`, `signal`.
- `Project Structure Steward`: `architecture`, `module boundaries`, `dependency direction`, `ownership`, `layering`.
- `Cross-Stack Cleanup Coordinator`: `backend + frontend`, `cross-stack`, `api contract`, `end-to-end cleanup`.

Tie-breaker order when multiple bots match:

1. If the task explicitly includes both frontend and Python/backend scope, choose `Cross-Stack Cleanup Coordinator`.
2. If the task mentions tests/coverage as the primary objective, choose `Python Test Expansion`.
3. If the task mentions modeling/research/backtesting as the primary objective, choose `Python Statistical Modeling`.
4. If the task is architecture/module-boundary focused, choose `Project Structure Steward`.
5. Otherwise choose the most specific single-domain cleanup bot (`Frontend Code Cleanup` or `Python Code Cleanup`).

If multiple bots seem valid, default to `Cross-Stack Cleanup Coordinator` and state why.

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

1. Trigger: `select bot:`
	- Action: routes the task to the most appropriate specialized bot, shows recommendation/reason, and asks whether to proceed.
	- Example: `select bot: expand tests for trading reporting edge cases`

2. Trigger: `help`
	- Action: prints this shortcut catalog.
	- Example: `help`

3. Trigger: `commit message git`
	- Action: returns commit subject options based on current uncommitted git changes (staged + unstaged), without project-manager context.
	- Example: `commit message git`

4. Trigger: `commit message task`
	- Action: runs the project-manager commit-context workflow and returns task-aligned commit subject options.
	- Example: `commit message task`

5. Trigger: `run checks`
	- Action: runs `python -m scripts.run_checks --profile quick` and reports test/audit outcomes.
	- Example: `run checks`

6. Trigger: `update documentation`
	- Action: runs `python -m scripts.checks.readme_check --repo-root . --max-age-days 90` and reports documentation findings.
	- Example: `update documentation`

7. Trigger: `run reference doc checks`
	- Action: runs `python -m scripts.reference_docs.check` and reports Financial & Market, Software, and API reference sync status together.
	- Example: `run reference doc checks`

8. Trigger: `sync reference docs`
	- Action: synchronizes Finance, Software, and API markdown and UI surfaces from the canonical registries.
	- Example: `sync reference docs`

9. Trigger: `run all checks`
	- Action: runs `python -m scripts.run_checks --profile ci` for docs checks, audits, and test suites.
	- Example: `run all checks`
