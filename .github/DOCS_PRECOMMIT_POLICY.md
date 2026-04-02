# Documentation and Validation Policy

All bots working in this repository must follow this policy when making changes that affect documentation, APIs, commands, or UI.

## 1) Documentation Trigger Matrix

If any trigger below applies to your change, update the corresponding docs in the same change set.

### A. API routes added/removed/renamed/behavior-changed

Automated steps (run first):

1. Run `sync reference docs` — parses `paper_trading_ui/backend/routes` via AST and updates `api.json` automatically.
2. Run `run reference doc checks` — verifies `api.json` is in sync with live FastAPI routes. Must pass before closing work.

Manual steps (bots cannot automate these):

3. If user-facing behavior changed, update relevant narrative docs:
   - `README.md`
   - `docs/README.md`
   - `trading/README.md` (if trading workflow is affected)
4. If new terminology appears in routes or payloads, add/update the definition in `docs/reference/Finance.md` (manually curated).

### B. Command/module/path changes (CLI paths, script paths, endpoint paths, import paths exposed to users)

Required updates:

1. Update all impacted README references that mention those paths.
2. Update `docs/README.md` index links when destinations or meaning changed.
3. If architecture ownership changed, update `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.

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

1. `python -m mypy paper_trading_ui/backend trading --python-version 3.14 --ignore-missing-imports --follow-imports=skip`
2. `python -m pytest`
3. `python -m scripts.checks.readme_check`
4. Frontend checks (when frontend changed):
   - `npm run lint`
   - `npm run typecheck`
   - `npm run test:coverage`

Document clearly why the full pass could not run.

## 6) Chat Shortcuts

Use these trigger phrases in chat to invoke the corresponding validation workflow.

### Full Pass

- `run all checks` — runs `python -m scripts.run_checks --profile ci`
- `update documentation` — runs `python -m scripts.checks.readme_check --max-age-days 90`

