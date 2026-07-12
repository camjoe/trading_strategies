# Plans Index

Type: index
Status: Active
Created: 2026-07-09
Last Reviewed: 2026-07-09
Purpose: Navigation index for independent deferred or remaining workstreams that no longer belong in the root status tracker.
Related: [Status](../status.md), [Overview](../overview.md), [Docs Map](../maps/docs-map.md)

## Overview

These files describe independent workstreams that are not part of one active implementation plan.
Each file records the current trigger, known decisions, and implementation shape to revisit when the
work becomes justified.

## Workstreams

| File | Workstream | Revisit when |
|---|---|---|
| [plug-and-play-strategy-catalog.md](plug-and-play-strategy-catalog.md) | P6 - plug-and-play strategy catalog | There is concrete demand to add or tune strategy variants without deploys |
| [parameter-optimization.md](parameter-optimization.md) | P11 - parameter optimization | Systematic parameter sweeps become an active need |

## Usage

Start with [status.md](../status.md) for the current active/deferred split. Open one of these plan
files only when its trigger is met or when updating the related subsystem.

## Boundaries

- These are not active commitments. `docs/status.md` remains the current status summary.
- Durable accepted decisions belong in `docs/adr/`, not in plan files.
- Completed phase narrative belongs in git history unless it explains current behavior.
