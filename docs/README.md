# Docs Index

Navigation index for docs and README files across the repository.

## Start Here

1. `../README.md` for the repository overview.
2. `../trading/README.md` for paper trading commands and scheduler operations.
3. Daily snapshot scheduler details are in `../trading/README.md` under "Daily Snapshot Scheduler (Cross-Platform)".

**Execution Note:**
All trading scripts must be run as Python modules from the repository root, e.g.,
```sh
python -m trading.paper_trading
```

## Docs Folder Files

- `Strategies.md`: strategy hypotheses and evaluation framework.
- `TODO.md`: active backlog and docs freshness checklist.
- `backtesting.md`: backtesting workflows, safeguards, and notes.
- `reference/Glossary.md`: finance, options, backtesting, and indicator terms.

## Docs Freshness Workflow

Use the docs freshness checker before commit or in CI to detect stale documentation for changed code areas.

```sh
python scripts/check_docs_freshness.py
python scripts/check_docs_freshness.py --base-ref origin/main --head-ref HEAD
```

- Default mode checks working tree + untracked files.
- CI mode uses a git ref diff and exits non-zero when docs are stale.
- `scripts/ci_smoke.py --skip-frontend` includes this check by default.
