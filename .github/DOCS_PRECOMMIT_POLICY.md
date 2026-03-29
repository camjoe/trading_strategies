# Documentation and Validation Policy

All bots working in this repository must follow this policy when making changes that affect documentation, APIs, commands, or UI.

## 1) Documentation Trigger Matrix

If any trigger below applies to your change, update the corresponding docs in the same change set.

### A. API routes added/removed/renamed/behavior-changed

Required updates:

1. Update `paper_trading_ui/README.md` under Core API Routes.
2. Verify route source remains accurate in `paper_trading_ui/backend/main.py`.
3. If user-facing behavior changed, update relevant workflow docs:
   - `README.md`
   - `docs/README.md`
   - `trading/README.md` (if trading workflow is affected)
4. If new terminology appears in routes or payloads, add/update the definition in `docs/reference/Glossary.md`.

### B. Command/module/path changes (CLI paths, script paths, endpoint paths, import paths exposed to users)

Required updates:

1. Update all impacted README references that mention those paths.
2. Update `docs/README.md` index links when destinations or meaning changed.
3. If architecture ownership changed, update `docs/architecture/trading-module-boundaries.md`.

## 2) Documentation Completeness Requirement

Do not close work as complete when documentation is stale for triggered areas.

If docs are intentionally deferred:

1. Explicitly state the deferral reason.
2. Add a follow-up task note in the final summary.
3. Do not claim the change is fully complete.

## 3) Required Validation Commands

Run both commands from the repo root and report pass/fail for each:

```sh
python -m scripts.run_checks --profile ci
```

```sh
python -m scripts.checks.readme_check --max-age-days 90
```

Both must be run and their outcomes included in the bot summary. Do not skip either without explicit user instruction.

## 4) Required Bot Summary

The bot summary must include:

1. Which trigger(s) were hit from Section 1.
2. Which docs/UI files were updated.
3. Exact validation commands run and their pass/fail status.
4. Any skipped checks and why.
5. Whether the change is commit-ready or blocked.

## 5) Fallback Checklist (When full pass cannot run)

If `python -m scripts.run_checks --profile ci` cannot run due to environment constraints, run and report at minimum:

1. `python -m mypy paper_trading_ui/backend trading --python-version 3.12 --ignore-missing-imports --follow-imports=skip`
2. `python -m pytest`
3. `python -m scripts.checks.readme_check`
4. Frontend checks (when frontend changed):
   - `npm run lint`
   - `npm run typecheck`
   - `npm run test:coverage`

Document clearly why the full pass could not run.

## 6) Request Templates

Use these prompts in chat to request a consistent pass from any bot.

### Full Pass

Run a full validation and docs audit pass for my current changes. Check documentation triggers (routes, paths, UI terms/pages), update docs if needed, run `python -m scripts.run_checks --profile ci` and `python -m scripts.checks.readme_check --max-age-days 90`, then summarize what changed, what checks ran, and any gaps.

### Fast Pass

Run a quick validation and docs audit pass for my current changes. At minimum run `python -m scripts.checks.readme_check` plus mypy and targeted tests for touched modules, then summarize findings and any docs updates needed.

### Docs-Only

Do a docs impact audit for my current changes. Focus on route changes, path or README updates, glossary term updates, and UI page doc alignment. Apply doc updates where needed and summarize.

### Optional Add-Ons

Add one of these lines to any prompt above when needed:

- Treat this as Linux-sensitive for path and typing behavior.
- Include frontend lint, typecheck, and coverage checks.
- Use fallback checks if the full CI run cannot complete, and explain why.
- Provide a concise commit-readiness verdict at the end.

