# Docs Index

Navigation index for the `docs/` folder and related documentation across the repository.

## Start Here

- [`../docs/file-map.md`](file-map.md) — top-level directory index with links to per-app maps and the nav guide
- [`../docs/architecture/nav-guide.md`](architecture/nav-guide.md) — task-oriented "I want to X → look/edit Y" lookup

**Execution note:** Run all trading scripts as Python modules from the repository root with the active venv interpreter, e.g.:
```sh
.venv/Scripts/python -m trading.interfaces.cli.main   # Windows
.venv/bin/python -m trading.interfaces.cli.main        # macOS/Linux
```

## Architecture Reference

**Canonical rules and conventions:**
- `.github/BOT_ARCHITECTURE_CONVENTIONS.md` — layering, dependency direction, naming, and package ownership

**Architecture maps** (`docs/maps/`):
- `docs/maps/trading-package-map.md` — `trading/` module directory
- `docs/maps/ui-map.md` — `paper_trading_ui/` structure
- `docs/maps/scripts-map.md` — `scripts/` tooling
- `docs/maps/docs-map.md` — documentation file inventory and staleness guide

**Architecture conventions** (`docs/architecture/`):
- `docs/architecture/service-cookbook.md` — task-oriented API reference ("what function do I call to do X?")
- `docs/architecture/service-repository-boundary.md` — service/repository contract rules

## Reference Notes and ADRs

Full listing: [`docs/reference/`](reference/). Key entries:

- `reference/notes-backtesting.md` — backtesting commands, safeguards, and layering overview
- `reference/notes-broker-integration.md` — broker abstraction, IB connection setup, live-trading safety
- `reference/notes-db-migration-system.md` — hand-rolled SQLite migration system reference
- `reference/adr-backtesting-layering.md` — decision rationale for backtesting module layering
- `reference/adr-cross-platform-paths.md` — pathlib cross-platform usage decision record
- `reference/adr-sleeve-virtualization-architecture.md` — sleeve virtualization architecture decision

## Workflows

1. Use [`docs/architecture/nav-guide.md`](architecture/nav-guide.md) to locate the right file for a change.
2. Run `python -m scripts.run_checks --profile ci` for primary mechanical checks.
3. Use `.github/DOCS_PRECOMMIT_POLICY.md` for the docs-impact checklist.
