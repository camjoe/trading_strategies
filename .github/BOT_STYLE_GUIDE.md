# Bot Style Guide

Purpose: keep code and documentation output consistent without forcing style-only churn.

Scope:

1. This file defines style/formatting behavior only.
2. Dependency direction, layering, naming ownership, abstraction/API contracts, and cross-platform rules live in `.github/BOT_ARCHITECTURE_CONVENTIONS.md`.

## Full Python style reference

See [`docs/style/python-style-guide.md`](../docs/style/python-style-guide.md) for the complete, curated
PEP 8 interpretation for this project. That document is the authoritative reference for both developers
and bots. Key project choices at a glance:

| Rule | This project |
|---|---|
| Max line length | **119 characters** |
| String quotes | Double quotes |
| Indentation | 4 spaces, no tabs |
| Type hints | Required for all public functions |
| Import order | stdlib → third-party → local |

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
3. Keep comments high-signal and concise — explain *why*, not *what*.
4. Use `from __future__ import annotations` at the top of every file.
5. Prefer `X | None` over `Optional[X]`; prefer lowercase `list[X]`, `dict[K, V]` over `typing` aliases.
6. Follow the naming table in `docs/style/python-style-guide.md`: `snake_case` functions/variables, `CapWords` classes, `UPPER_SNAKE_CASE` module-level constants.
7. Use f-strings for string formatting.
8. Do not use bare `except:` or `except Exception: pass`.

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
4. When generating new Python code, apply the rules in `docs/style/python-style-guide.md` by default.
