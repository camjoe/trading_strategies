# Docs Index

Navigation index for docs and README files across the repository.

## Start Here

1. `../README.md` for the repository overview.
2. `../trading/README.md` for paper trading commands and scheduler operations.
3. Scheduler details are in `../trading/README.md` under "Scheduler Operations".

**Execution Note:**
All trading scripts must be run as Python modules from the repository root, e.g.,
```sh
python -m trading.paper_trading
```

## Docs Folder Files

- `Strategies.md`: strategy hypotheses and evaluation framework.
- `backtesting.md`: backtesting workflows, safeguards, and notes.
- `architecture/backtesting-layering-adr.md`: decision rationale and guardrails for backtesting module layering.
- `architecture/strategy-encapsulation-notes.md`: strategy ownership map and prompt templates for a future strategy-class refactor.
- `architecture/runtime-job-coverage-follow-up.md`: prioritized testing backlog for low-coverage runtime and support modules.

## Architecture Reference

**Canonical rules and conventions:**
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md`: layering, dependency direction, naming, and package ownership.
- `.github/TRADING_EXECUTION_ROADMAP.md`: prioritized refactoring guidance and next structural improvements.

## Purpose

This docs index helps contributors find architecture guides, references, and the current documentation quality workflow.

## Workflows

1. Use this index to locate and update the source-of-truth document for changed behavior.
2. Run `python -m scripts.run_checks --profile ci` for primary mechanical checks.
3. Use `.github/DOCS_PRECOMMIT_POLICY.md` for docs-impact checklist and bot request templates.
