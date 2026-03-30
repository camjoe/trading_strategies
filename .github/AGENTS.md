# Workspace Bot Standard

Purpose: define how bots operate in this repository without unnecessary process overhead.

## Important Clarification

Specialized bots are still present and usable in `.github/agents/`:

- `cross-stack-cleanup.agent.md`: coordinate safe cleanup work across Python and frontend scopes.
- `frontend-code-cleanup.agent.md`: simplify frontend code while preserving behavior and type safety.
- `project-structure-steward.agent.md`: enforce module boundaries, dependency direction, and architecture consistency.
- `python-code-cleanup.agent.md`: refactor Python code for readability/maintainability without behavior changes.
- `python-stat-modeling.agent.md`: build and evaluate trading-focused statistical modeling workflows.
- `python-test-expansion.agent.md`: add and strengthen tests, edge cases, and regression coverage.

This file provides shared baseline rules; it does not replace or remove those agents.

## Canonical References

- Docs-impact and validation policy: `.github/DOCS_PRECOMMIT_POLICY.md`
- Script behavior and command flags: `scripts/README.md`
- Architecture boundaries: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Bot dependency/naming conventions: `.github/BOT_ARCHITECTURE_CONVENTIONS.md`
- Style approach and formatting expectations: `.github/BOT_STYLE_GUIDE.md`

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

## Default Validation Workflow

1. Day-to-day fast checks:
   - `python -m scripts.run_checks --profile quick`
2. Full cross-stack checks:
   - `python -m scripts.run_checks --profile ci`
3. Docs-quality focused audit:
   - `python -m scripts.checks.readme_check --max-age-days 90`

If a check cannot run, report what was skipped and why.

## Safe Command Allowlist (For Fewer Approval Clicks)

Use this list for workspace-level "always allow" command approvals:

- `python -m scripts.run_checks --profile quick`
- `python -m scripts.run_checks --profile quick --with-frontend`
- `python -m scripts.run_checks --profile ci`
- `python -m scripts.run_checks --profile ci --skip-frontend`
- `python -m scripts.checks.readme_check`
- `python -m scripts.checks.readme_check --max-age-days 90`
- `python -m pytest`
- `python -m mypy paper_trading_ui/backend trading --python-version 3.12 --ignore-missing-imports --follow-imports=skip`
- `npm run lint` (from `paper_trading_ui/frontend`)
- `npm run typecheck` (from `paper_trading_ui/frontend`)
- `npm run test:coverage` (from `paper_trading_ui/frontend`)

Note: approval prompts are controlled by your VS Code/Copilot environment; this file documents the intended allowlist.

