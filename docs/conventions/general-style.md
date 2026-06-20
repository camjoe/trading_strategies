# General Style Guide

Type: convention
Status: Active
Created: 2026-03-29
Last Reviewed: 2026-06-19
Purpose: Cross-cutting style approach + documentation/markdown style, and the index of per-language style guides.
Related: [Python Style](python-style.md), [Frontend Style](frontend-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

Scope:

1. This file defines the **cross-cutting style approach** and **documentation/markdown style**.
2. Per-language rules live in their own guides (see the index below).
3. Dependency direction, layering, naming ownership, and cross-platform rules live in [`architecture-conventions.md`](../architecture/architecture-conventions.md).

## Style guides by surface

| Surface | Guide |
|---|---|
| Python | [`python-style.md`](python-style.md) |
| TypeScript / frontend | [`frontend-style.md`](frontend-style.md) |
| Documentation / markdown | this file (below) |

## Style Approach

Use a single default mode: `balanced`.

Balanced means:

1. Prefer existing local style in touched files.
2. Apply consistency improvements when they reduce ambiguity or maintenance cost.
3. Avoid broad style-only churn.
4. Keep behavior unchanged unless explicitly requested.

## Documentation and Markdown

1. Prefer short sections with actionable bullets.
2. Keep architecture docs declarative and source-of-truth oriented.
3. Include runnable commands from the repository root where relevant.
