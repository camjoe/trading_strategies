# Docs Index

Navigation index for docs and README files across the repository.

## Start Here

1. `../README.md` for the repository overview.
2. `../trading/README.md` for paper trading commands, direct runtime job scripts, and scheduler operations.
3. Scheduler details are in `../trading/README.md` under "Scheduler Operations"; `manage_job_schedules.py` is the single job-schedule entrypoint, while the direct job scripts remain the runtime source of truth.

**Execution Note:**
All trading scripts should be run as Python modules from the repository root, preferably with the active venv interpreter, e.g.,
```sh
./venv/bin/python -m trading.interfaces.cli.main
```

## Docs Folder Files

- `reference/adr-backtesting-layering.md`: decision rationale for backtesting module layering.
- `reference/adr-cross-platform-paths.md`: decision record for always using pathlib; lessons from a Windows/Linux CI failure.
- `reference/notes-backtesting.md`: backtesting commands, safeguards, layering overview, and operational notes.
- `reference/notes-broker-integration.md`: broker abstraction layer — architecture, account configuration, IB connection setup, live trading safety guard, fill reconciliation, and extension guide.
- `reference/notes-db-migration-system.md`: active reference guide for the hand-rolled SQLite migration system.
- `reference/notes-sentiment-signals.md`: current-state map for sentiment/topic-driven strategies. Phase 4 implementation (news_sentiment, social_trend_rotation, policy_regime) is complete; remaining backlog tracked in PM.
- `reference/notes-strategies.md`: strategy catalog, implementation status, proxy feature descriptions, and evaluation framework guidance.
- `reference/notes-screenshot-ui.md`: UI screenshot utility — setup, usage, all flags, and recipes for developers and AI assistants.
- `reference/notes-strategy-design-decisions.md`: recorded architectural and design decisions from the initial strategy planning phase (optimization target, rotation scope, live hook seams, simulator compatibility).

## Architecture Reference

**Canonical rules and conventions:**
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`: layering, dependency direction, naming, and package ownership.

## Purpose

This docs index helps contributors find architecture guides, references, and the current documentation quality workflow.

## Workflows

1. Use this index to locate and update the source-of-truth document for changed behavior.
2. Run `python -m scripts.run_checks --profile ci` for primary mechanical checks.
3. Use `.github/DOCS_PRECOMMIT_POLICY.md` for docs-impact checklist and bot request templates.
