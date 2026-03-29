# Bot Style Guide

Purpose: keep code and documentation output consistent without forcing style-only churn.

Scope:

1. This file defines style/formatting behavior only.
2. Dependency direction, layering, naming ownership, abstraction/API contracts, and cross-platform rules live in `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.

## Style Approach

Use a single default mode: `balanced`.

Balanced means:

1. Prefer existing local style in touched files.
2. Apply consistency improvements when they reduce ambiguity or maintenance cost.
3. Avoid broad style-only churn.
4. Keep behavior unchanged unless explicitly requested.

## Language Expectations

### Python

1. Use explicit type hints for public functions and non-trivial returns.
2. Prefer small single-purpose helpers over large mixed-responsibility functions.
3. Keep comments high-signal and concise.

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
