---
name: Docs Sync
layer: portable
description: Portable starter skill for keeping README files, architecture notes, API docs, and operational documentation aligned with code changes.
use_when:
  - behavior changes without doc updates
  - documentation drift is likely
  - commands, routes, or workflows changed
localize_with:
  - documentation directories
  - freshness checks
  - docs ownership rules
---

## Goal

Keep human-facing documentation aligned with current behavior and workflows.

## Responsibilities

1. Identify code changes that imply documentation impact.
2. Find the source-of-truth docs for the changed behavior.
3. Update commands, paths, API descriptions, and workflow notes.
4. Flag gaps where documentation should exist but does not.

## Constraints

1. Do not rewrite docs broadly when only a targeted update is needed.
2. Do not change runtime behavior while syncing docs.
3. Do not leave code examples stale after changing commands or routes.

## Localize for a project

Fill in:

- canonical docs folders and README conventions
- docs freshness or precommit checks
- reference-doc generation or sync workflows

## Expected output

1. Impacted docs
2. Exact updates made
3. Remaining drift or follow-up items
