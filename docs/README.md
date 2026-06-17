# Docs Index

Type: index
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-06-16
Purpose: Navigation index for docs/ — folder guide, links to all maps and key reference docs.
Related: [Docs Map](maps/docs-map.md), [Doc Header Standard](conventions/doc-header-standard.md)

Navigation index for the `docs/` folder. See [`docs/maps/docs-map.md`](maps/docs-map.md) for the full file inventory with staleness tracking.

## Folder Guide

| Folder | Purpose |
|---|---|
| [`architecture/`](architecture/) | **How** the system is designed — layers, boundaries, service API |
| [`conventions/`](conventions/) | **Rules** this project follows — coding style, doc standards, naming |
| [`maps/`](maps/) | **Where** things live — file/directory maps, updated frequently |
| [`reference/`](reference/) | **Why** decisions were made (ADRs) and deep-dive notes on subsystems |
| [`runbooks/`](runbooks/) | **How to operate** — step-by-step procedures for humans or agents |

## Start Here

- [`maps/docs-map.md`](maps/docs-map.md) — full documentation inventory, top-level directory overview, and staleness guide
- [`architecture/nav-guide.md`](architecture/nav-guide.md) — task-oriented "I want to X → look/edit Y" lookup

**Execution note:** Run all trading scripts as Python modules from the repository root with the active venv interpreter, e.g.:
```sh
.venv/Scripts/python -m trading.interfaces.cli.main   # Windows
.venv/bin/python -m trading.interfaces.cli.main        # macOS/Linux
```

## Architecture

- [`architecture/service-cookbook.md`](architecture/service-cookbook.md) — which function to call for common tasks
- [`architecture/service-repository-boundary.md`](architecture/service-repository-boundary.md) — service/repository contract rules
- [`.github/BOT_ARCHITECTURE_CONVENTIONS.md`](../.github/BOT_ARCHITECTURE_CONVENTIONS.md) — authoritative layering and import boundary rules

## Maps (file/directory inventories)

- [`maps/trading-package-map.md`](maps/trading-package-map.md) — `trading/` module directory and layering rules
- [`maps/ui-map.md`](maps/ui-map.md) — `paper_trading_ui/` backend and frontend structure
- [`maps/scripts-map.md`](maps/scripts-map.md) — `scripts/` tooling inventory
- [`maps/docs-map.md`](maps/docs-map.md) — documentation file inventory

## Reference Notes and ADRs

Full listing: [`reference/`](reference/). Key entries:

- [`reference/notes-backtesting.md`](reference/notes-backtesting.md) — backtesting commands, safeguards, and layering overview
- [`reference/notes-broker-integration.md`](reference/notes-broker-integration.md) — broker abstraction, IB connection setup, live-trading safety
- [`reference/notes-db-migration-system.md`](reference/notes-db-migration-system.md) — hand-rolled SQLite migration system
- [`reference/adr-backtesting-layering.md`](reference/adr-backtesting-layering.md) — decision rationale for backtesting module layering
- [`reference/adr-cross-platform-paths.md`](reference/adr-cross-platform-paths.md) — pathlib cross-platform usage decision record

## Conventions

- [`conventions/python-style-guide.md`](conventions/python-style-guide.md) — Python coding conventions for this repo
- [`conventions/readme-layout-standard.md`](conventions/readme-layout-standard.md) — standard README section layout
- [`conventions/reference-doc-standard.md`](conventions/reference-doc-standard.md) — standard structure for reference notes

## Runbooks

- [`runbooks/README.md`](runbooks/README.md) — runbook index with quick-start commands
- [`runbooks/daily_operations.md`](runbooks/daily_operations.md) — daily paper-trading job monitoring
- [`runbooks/burn_in_protocol.md`](runbooks/burn_in_protocol.md) — burn-in protocol for new strategies
- [`runbooks/governance_review_guide.md`](runbooks/governance_review_guide.md) — weekly/monthly governance review

## Keeping Docs Fresh

Run `/update-docs` to refresh maps and the service cookbook after adding files, renaming paths, or adding service functions. When making smaller targeted changes, update the relevant map in `docs/maps/` directly.
