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
- `architecture/trading-module-boundaries.md`: module ownership and dependency direction for trading.
- `reference/Glossary.md`: finance, options, backtesting, and indicator terms.

## Docs Freshness Workflow

Use the docs freshness checker before commit or in CI to detect stale documentation for changed code areas.

```sh
python -m scripts.check_docs_freshness
python -m scripts.check_docs_freshness --base-ref origin/main --head-ref HEAD
```

- Default mode checks working tree + untracked files.
- CI mode uses a git ref diff and exits non-zero when docs are stale.
- `python -m scripts.ci_smoke --skip-frontend` includes this check by default.
