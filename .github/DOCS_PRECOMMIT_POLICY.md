# Documentation and Validation Policy

Follow this policy when a change affects documentation, public behavior, commands, API routes, or UI-visible workflows.

## 1. Trigger Matrix

If any trigger applies, update the corresponding docs in the same change set unless the user explicitly approves deferral.

### A. API routes or payload behavior changed

Examples:

- route added, removed, or renamed
- request or response shape changed
- endpoint semantics changed in a user-visible way

Required updates:

1. Run `sync reference docs` to refresh `paper_trading_ui/frontend/src/assets/api.json`.
2. Run `run reference doc checks` to verify API and software registries are in sync.
3. Update narrative docs when user-facing behavior changed:
   - `README.md`
   - `docs/README.md`
   - `paper_trading_ui/README.md`
   - `trading/README.md` when trading workflows are affected
4. If new terminology or domain concepts were introduced, update the relevant manually curated reference notes under `docs/reference/` or `paper_trading_ui/frontend/src/assets/finance.json` when the UI docs depend on that content.

### B. Commands, paths, or module locations changed

Examples:

- CLI commands or script invocation changed
- import paths exposed to users changed
- README examples or setup paths changed

Required updates:

1. Update all affected README references.
2. Update `docs/README.md` when index links or destinations changed.
3. Update architecture guidance only when ownership or layering expectations changed:
   - `.github/BOT_ARCHITECTURE_CONVENTIONS.md`

### C. UI workflows or operator behavior changed

Examples:

- admin or account workflows changed
- backtest or runtime flows changed in the UI
- docs assets shown in the UI changed

Required updates:

1. Update the relevant README or docs page that describes the workflow.
2. If UI documentation assets changed, run the reference docs sync/check flow as appropriate.

## 2. Completeness Rule

Do not mark work complete when triggered documentation is stale.

If docs are intentionally deferred:

1. State the deferral explicitly.
2. Include the reason.
3. Call out the follow-up work in the final summary.
4. Do not describe the change as fully complete.

## 3. Validation Expectations

From the repo root, run and report:

```sh
python -m scripts.run_checks --profile ci
python -m scripts.checks.readme_check --max-age-days 90
```

When reference docs are part of the change, also run:

```sh
python -m scripts.documentation_ui.check
```

Do not skip relevant validation without explicit user instruction or a documented environment constraint.

## 4. Fallback When Full Validation Cannot Run

If the full CI-shaped pass cannot run, report why and run the closest practical subset:

1. `python -m pytest`
2. `python -m mypy paper_trading_ui/backend trading --ignore-missing-imports`
3. `python -m scripts.checks.readme_check --max-age-days 90`
4. Frontend checks when frontend code changed:
   - `npm run lint`
   - `npm run typecheck`
   - `npm run test:coverage`
5. `python -m scripts.documentation_ui.check` when reference docs or UI docs assets changed

## 5. Required Final Summary

The final summary must include:

1. Which trigger areas were hit
2. Which docs or docs assets were updated
3. Exact validation commands run and pass/fail status
4. Any skipped checks and why
5. Whether the work is complete or documentation follow-up remains

## 6. Shortcut Alignment

The policy aligns with these repo shortcuts:

- `sync docs`
- `run reference doc checks`
- `sync reference docs`
- `update documentation`
- `run all checks`
