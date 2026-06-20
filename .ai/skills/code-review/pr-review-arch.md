---
name: pr-review-arch
description: Reviews architecture constraints in a PR diff — layer violations, dependency direction, and wrong-layer logic.
---

# PR Review — Architecture

Scope: branch diff only (`git diff --name-only <base>...HEAD`). Do not expand to unchanged files.

## What to check

1. **Layer violations** — does any changed file import across a forbidden boundary? Run `layer_check` first; if it passed, look for subtler violations not caught statically.
2. **Dependency direction** — do services depend on interfaces? Do repositories call services? Flag it.
3. **Wrong-layer logic** — business rules in repositories, data access in services, HTTP concerns leaking into domain code.
4. **New abstractions** — is a new base class, mixin, or protocol being introduced? Does it belong in this layer?

Read `docs/architecture/architecture-conventions.md` before reviewing `trading/`.

## Severity

- **VIOLATION** — blocks the PR. The code cannot be merged as-is.
- **CONCERN** — advisory. Worth noting; user decides whether to fix before merging.

## Output format

```
VIOLATION | trading/services/foo.py:42 | Service imports from interface layer (SomeRouter)
CONCERN   | trading/repositories/bar.py:18 | Business logic in repository method; consider moving to service
```

One line per finding. File and line required. No findings → `Architecture: Clean`.

## Repo references

- [architecture-review.md](architecture-review.md)
- `docs/architecture/architecture-conventions.md`
- `scripts/checks/layer_check.py`
