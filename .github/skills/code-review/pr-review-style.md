---
name: pr-review-style
description: Reviews style compliance in a PR diff — naming, structure, and conventions beyond what ruff enforces.
---

# PR Review — Style

Scope: branch diff only. Do not flag ruff-catchable violations — those are handled by `validate-code`.

## What to check

Ruff handles formatting and basic lint. This pass covers what ruff does **not** enforce:

1. **Naming** — are names consistent with the surrounding codebase? (snake_case functions, PascalCase classes, UPPER_CASE constants, `_private` prefix for internals)
2. **Docstrings and comments** — are public functions and classes documented? Are inline comments explaining "why", not "what"?
3. **Module organization** — are imports grouped (stdlib → third-party → local)? Are large functions split into helper functions with meaningful names?
4. **Consistency** — does the new code match patterns already established in the same file or service? No unexplained style drift.
5. **Dead code** — commented-out blocks, unused imports ruff didn't catch, `TODO` items without a ticket reference.

Read `.github/BOT_STYLE_GUIDE.md` and `docs/style/python-style-guide.md` before reviewing.

## Severity

- **BLOCKER** — a style violation that actively harms readability or maintainability (e.g., a public API with no docstring, misleading variable name in a critical path).
- **ADVISORY** — minor style inconsistency worth noting but not worth a round-trip.

## Output format

```
BLOCKER  | trading/services/foo.py:15 | Public method `do_thing` has no docstring
ADVISORY | trading/services/foo.py:62 | Variable `d` is ambiguous; prefer `duration_seconds`
```

One line per finding. No findings → `Style: Clean`.

## Repo references

- `.github/BOT_STYLE_GUIDE.md`
- `docs/style/python-style-guide.md`
