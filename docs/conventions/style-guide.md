# Bot Style Guide

Type: convention
Status: Active
Created: 2026-03-29
Last Reviewed: 2026-06-17
Purpose: Keep code and documentation output consistent without forcing style-only churn.
Related: [Python Style](python-style.md), [Architecture Conventions](../architecture/architecture-conventions.md)

Scope:

1. This file defines style/formatting behavior only.
2. Dependency direction, layering, naming ownership, abstraction/API contracts, and cross-platform rules live in `docs/architecture/architecture-conventions.md`.

## Full Python style reference

Python style rules live in **[`python-style.md`](python-style.md)** — the complete, curated PEP 8
interpretation for this project, and the authoritative reference for both developers and bots. Do not
restate Python rules here; link to that document so the two never drift.

## Style Approach

Use a single default mode: `balanced`.

Balanced means:

1. Prefer existing local style in touched files.
2. Apply consistency improvements when they reduce ambiguity or maintenance cost.
3. Avoid broad style-only churn.
4. Keep behavior unchanged unless explicitly requested.

## Language Expectations

### Python

All Python style rules — type hints, imports, naming, docstrings, idioms — are in
[`python-style.md`](python-style.md). Naming ownership and model suffixes (`*Config`/`*Insert`/`*Record`)
live in [`architecture-conventions.md`](../architecture/architecture-conventions.md).

### TypeScript and Frontend

1. Keep components focused and strongly typed.
2. Favor composition over large monolithic components.
3. Preserve existing design system patterns when present.
4. If no design system exists and restyling is requested, define theme tokens (CSS variables) before per-component styles.

### Markdown and Docs

1. Prefer short sections with actionable bullets.
2. Keep architecture docs declarative and source-of-truth oriented.
3. Include runnable commands from repository root where relevant.

## Bot Output Expectations

1. Use the balanced style approach unless the user explicitly asks otherwise.
2. Explain non-trivial style decisions in the final summary.
3. Do not do style-only rewrites unless explicitly requested.
4. When generating new Python code, apply the rules in `docs/conventions/python-style.md` by default.
