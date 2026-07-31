# Docs Index

Type: index
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-21
Purpose: Navigation index for docs/ — folder guide, links to all maps and key reference docs.
Related: [Docs Map](maps/docs-map.md), [Documentation Authoring Standard](conventions/docs-authoring.md)

## Overview

Navigation index for the `docs/` folder. See [`docs/maps/docs-map.md`](maps/docs-map.md) for the full file inventory with staleness tracking.

## Folder Guide

| Folder | Purpose |
|---|---|
| [`architecture/`](architecture/) | **How** the system is designed — layers, boundaries, service API |
| [`conventions/`](conventions/) | **Rules** this project follows — coding style, doc standards, naming |
| [`maps/`](maps/) | **Where** things live — file/directory maps, updated frequently |
| [`reference/`](reference/) | **Why** decisions were made (ADRs) and deep-dive notes on subsystems |
| [`runbooks/`](runbooks/) | **How to operate** — step-by-step procedures for humans or agents |

## Quick Start

- [`overview.md`](overview.md) — **start here**: current capabilities, concepts, architecture,
  limitations, and scope
- [`maps/docs-map.md`](maps/docs-map.md) — full documentation inventory, top-level directory overview, and staleness guide
- [`architecture/nav-guide.md`](architecture/nav-guide.md) — task-oriented "I want to X → look/edit Y" lookup
- [`adr/`](adr/) — durable architecture and product decisions

**Execution note:** Activate the repository virtual environment described in the root README, then
run commands as Python modules from the repository root:

```sh
python -m trading.interfaces.cli.main
```

## Architecture

- [`architecture/service-cookbook.md`](architecture/service-cookbook.md) — which function to call for common tasks
- [`architecture/service-ownership.md`](architecture/service-ownership.md) — per-service ownership boundaries (owns / does not own)
- [`architecture/service-repository-boundary.md`](architecture/service-repository-boundary.md) — service/repository contract rules
- [`docs/architecture/architecture-conventions.md`](../docs/architecture/architecture-conventions.md) — authoritative layering and import boundary rules

## Maps (file/directory inventories)

- [`maps/trading-package-map.md`](maps/trading-package-map.md) — `src/trading/` module directory and layering rules
- [`maps/ui-map.md`](maps/ui-map.md) — `apps/paper_trading_web/` backend and frontend structure
- [`maps/scripts-map.md`](maps/scripts-map.md) — `scripts/` tooling inventory
- [`maps/docs-map.md`](maps/docs-map.md) — documentation file inventory

## Reference Notes and ADRs

Full listing: [`reference/`](reference/). Key entries:

- [`reference/backtesting.md`](reference/backtesting.md) — backtesting commands, walk-forward terminology, safeguards, and layering overview
- [`reference/broker-integration.md`](reference/broker-integration.md) — broker abstraction, adapter wiring, live-trading safety
- [`reference/ibkr-paper-execution-plan.md`](reference/ibkr-paper-execution-plan.md) — target auto-trader shape, audited current-state gap, and the phase order to close it
- [`reference/broker-setup-ibkr.md`](reference/broker-setup-ibkr.md) — IBKR Client Portal Gateway operator setup and connection checklist
- [`reference/retired-strategy-primitives.md`](reference/retired-strategy-primitives.md) � decision rules and default thresholds of six strategy primitives removed from the registry, kept so any can be rebuilt
- [`reference/financial-market-knowledge.md`](reference/financial-market-knowledge.md) — canonical finance, market, and strategy glossary source for the documentation UI
- [`reference/runtime-jobs.md`](reference/runtime-jobs.md) — runtime job entrypoints: how to run and schedule each one
- [`reference/db-migration-system.md`](reference/db-migration-system.md) — numbered Alembic migration system: revisions, operator commands, runtime verification
- [`reference/database-reset-plan.md`](reference/database-reset-plan.md) — planned migration-chain squash and data reset: per-table drop/preserve decisions and open questions
- [`reference/database-transactions.md`](reference/database-transactions.md) — the `unit_of_work` / `commit_unit_of_work` pattern for atomic multi-write database operations
- [`reference/performance-and-risk-tables.md`](reference/performance-and-risk-tables.md) — grain, period, and exact column meanings for equity_snapshots, daily_metrics, and risk_snapshots (plus the books exit-threshold columns)
- [`reference/rotation-scoring.md`](reference/rotation-scoring.md) — champion/challenger rotation score components and their data sources
- [`reference/database-diagram-viewer.html`](reference/database-diagram-viewer.html) — interactive generated database diagram viewer with full columns, grouped sections, and FK arrows
- [`adr/017-ibkr-paper-broker-type.md`](adr/017-ibkr-paper-broker-type.md) — IBKR paper is its own broker type with a paper-account assertion; `live_trading_enabled` guards real money only
- [`adr/016-optimizer-experiments-as-research-evidence.md`](adr/016-optimizer-experiments-as-research-evidence.md) — promotion, rotation, and evaluation read optimizer experiments; the rolling-window path is retired
- [`adr/015-numbered-alembic-migrations.md`](adr/015-numbered-alembic-migrations.md) — numbered Alembic revisions replace probe-based schema init; runtime is verify-only
- [`adr/014-execution-mode-collapse.md`](adr/014-execution-mode-collapse.md) — one book-keyed runtime path; rotation scheduling is book-owned
- [`adr/012-runtime-alert-email-configuration.md`](adr/012-runtime-alert-email-configuration.md) — runtime SMTP alerts use environment configuration
- [`adr/010-book-keyed-execution-model.md`](adr/010-book-keyed-execution-model.md) — books are the execution primitive after sleeve retirement
- [`adr/008-production-runtime-hosting-and-deployment.md`](adr/008-production-runtime-hosting-and-deployment.md) — dedicated Linux host runs jobs from a `main`-tracking checkout; blue/green deferred
- [`adr/006-cross-cutting-decorators.md`](adr/006-cross-cutting-decorators.md) — sanctioned decorator/context-manager pattern for cross-cutting concerns
- [`adr/005-models-as-lowest-data-layer.md`](adr/005-models-as-lowest-data-layer.md) — models/ holds all passive data contracts as the lowest layer; feature subfolders
- [`adr/004-runtime-naming-and-operational-settings.md`](adr/004-runtime-naming-and-operational-settings.md) — disambiguate "runtime" naming; operational_settings package

## Conventions

- [`conventions/python-style.md`](conventions/python-style.md) — Python coding conventions for this repo
- [`conventions/readme-layout.md`](conventions/readme-layout.md) — standard README section layout
- [`conventions/docs-authoring.md`](conventions/docs-authoring.md) — required doc headers, doc types, templates, and reference-doc/ADR section layouts
- [`conventions/documentation-maintenance.md`](conventions/documentation-maintenance.md) — anti-doc-rot principles and documentation drift-check practices

## Runbooks

- [`runbooks/README.md`](runbooks/README.md) — runbook index with quick-start commands
- [`runbooks/production-runtime-host.md`](runbooks/production-runtime-host.md) — Linux production host setup + test-and-deploy workflow
- [`runbooks/runtime-operations.md`](runbooks/runtime-operations.md) — daily + weekly-backup job monitoring and recovery
- [`runbooks/burn-in-protocol.md`](runbooks/burn-in-protocol.md) — burn-in protocol for new strategies
- [`runbooks/governance-review.md`](runbooks/governance-review.md) — weekly/monthly governance review

## Keeping Docs Fresh

Run `/update-docs` to refresh maps and the service cookbook after adding files, renaming paths, or adding service functions. When making smaller targeted changes, update the relevant map in `docs/maps/` directly.
