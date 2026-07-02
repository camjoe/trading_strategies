# Docs Index

Type: index
Status: Active
Created: 2026-03-01
Last Reviewed: 2026-07-02
Purpose: Navigation index for docs/ — folder guide, links to all maps and key reference docs.
Related: [Docs Map](maps/docs-map.md), [Doc Header Standard](conventions/doc-header.md)

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

- [`overview.md`](overview.md) — **start here**: definitive explainer of what the app is, what it can do today (with honest gaps), how it works, and the north-star plan
- [`maps/docs-map.md`](maps/docs-map.md) — full documentation inventory, top-level directory overview, and staleness guide
- [`architecture/nav-guide.md`](architecture/nav-guide.md) — task-oriented "I want to X → look/edit Y" lookup
- [`plan.md`](plan.md) — **the tracker**: priority board (P1..N + commitment), status, and timelines
- [`decisions.md`](decisions.md) — **what needs defining**: the consolidated list of open decisions
- [`sleeves-accounts-convergence.md`](sleeves-accounts-convergence.md) — design detail for converging account and sleeve trading paths onto shared services
- [`db-schema-rewrite-spec.md`](db-schema-rewrite-spec.md) — draft target schema for a clean, goals-aligned database rewrite (the convergence "option B", greenfield, no data migration)
- [`db-schema-target.md`](db-schema-target.md) — the proposed final schema on its own (WIP), without old-schema/change framing
- [`developer-notes.md`](developer-notes.md) — developer working notes, gotchas, and pre-implementation checks
- [`implementation/`](implementation/) — per-initiative implementation guides (self-contained work orders an agent can execute end-to-end): [p2-evaluation-contract-tests.md](implementation/p2-evaluation-contract-tests.md) (template + example), [p1-execution-loop.md](implementation/p1-execution-loop.md) (the keystone), [p3-db-schema-rewrite.md](implementation/p3-db-schema-rewrite.md) (the schema rewrite)

**Execution note:** Run all trading scripts as Python modules from the repository root with the active venv interpreter, e.g.:
```sh
.venv/Scripts/python -m trading.interfaces.cli.main   # Windows
.venv/bin/python -m trading.interfaces.cli.main        # macOS/Linux
```

## Architecture

- [`architecture/service-cookbook.md`](architecture/service-cookbook.md) — which function to call for common tasks
- [`architecture/service-repository-boundary.md`](architecture/service-repository-boundary.md) — service/repository contract rules
- [`docs/architecture/architecture-conventions.md`](../docs/architecture/architecture-conventions.md) — authoritative layering and import boundary rules
- [`architecture/restructure-notes.md`](architecture/restructure-notes.md) — `src/` restructure notes: outcome, reusable patterns, and the open domain-slicing question (foundation phase complete)

## Maps (file/directory inventories)

- [`maps/trading-package-map.md`](maps/trading-package-map.md) — `src/trading/` module directory and layering rules
- [`maps/ui-map.md`](maps/ui-map.md) — `apps/paper_trading_web/` backend and frontend structure
- [`maps/scripts-map.md`](maps/scripts-map.md) — `scripts/` tooling inventory
- [`maps/docs-map.md`](maps/docs-map.md) — documentation file inventory

## Reference Notes and ADRs

Full listing: [`reference/`](reference/). Key entries:

- [`reference/backtesting.md`](reference/backtesting.md) — backtesting commands, safeguards, and layering overview
- [`reference/broker-integration.md`](reference/broker-integration.md) — broker abstraction, adapter wiring, live-trading safety
- [`reference/broker-setup-ibkr.md`](reference/broker-setup-ibkr.md) — IBKR Client Portal Gateway operator setup and connection checklist
- [`reference/runtime-jobs.md`](reference/runtime-jobs.md) — runtime job entrypoints: how to run and schedule each one
- [`reference/broker-setup-alpaca.md`](reference/broker-setup-alpaca.md) — Alpaca setup guide (Draft — adapter not yet implemented)
- [`reference/db-migration-system.md`](reference/db-migration-system.md) — hand-rolled SQLite migration system
- [`adr/008-production-runtime-hosting-and-deployment.md`](adr/008-production-runtime-hosting-and-deployment.md) — dedicated Linux host runs jobs from a `main`-tracking checkout; blue/green deferred
- [`adr/006-cross-cutting-decorators.md`](adr/006-cross-cutting-decorators.md) — sanctioned decorator/context-manager pattern for cross-cutting concerns
- [`adr/005-models-as-lowest-data-layer.md`](adr/005-models-as-lowest-data-layer.md) — models/ holds all passive data contracts as the lowest layer; feature subfolders
- [`adr/004-runtime-naming-and-operational-settings.md`](adr/004-runtime-naming-and-operational-settings.md) — disambiguate "runtime" naming; operational_settings package
- [`adr/003-sleeve-virtualization-architecture.md`](adr/003-sleeve-virtualization-architecture.md) — sleeve virtualization architecture decision record
- [`adr/002-backtesting-layering.md`](adr/002-backtesting-layering.md) — decision rationale for backtesting module layering
- [`adr/001-cross-platform-paths.md`](adr/001-cross-platform-paths.md) — pathlib cross-platform usage decision record

## Conventions

- [`conventions/python-style.md`](conventions/python-style.md) — Python coding conventions for this repo
- [`conventions/readme-layout.md`](conventions/readme-layout.md) — standard README section layout
- [`conventions/reference-doc.md`](conventions/reference-doc.md) — standard structure for reference notes
- [`conventions/documentation-maintenance.md`](conventions/documentation-maintenance.md) — anti-doc-rot principles + deferred doc-tooling backlog

## Runbooks

- [`runbooks/README.md`](runbooks/README.md) — runbook index with quick-start commands
- [`runbooks/production-runtime-host.md`](runbooks/production-runtime-host.md) — Linux production host setup + test-and-deploy workflow
- [`runbooks/runtime-operations.md`](runbooks/runtime-operations.md) — daily + weekly-backup job monitoring and recovery
- [`runbooks/burn-in-protocol.md`](runbooks/burn-in-protocol.md) — burn-in protocol for new strategies
- [`runbooks/governance-review.md`](runbooks/governance-review.md) — weekly/monthly governance review

## Keeping Docs Fresh

Run `/update-docs` to refresh maps and the service cookbook after adding files, renaming paths, or adding service functions. When making smaller targeted changes, update the relevant map in `docs/maps/` directly.
