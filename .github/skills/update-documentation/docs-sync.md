---
name: docs-sync
description: Keep README files, architecture notes, API docs, and operational documentation aligned with code changes.
---

# Docs Sync

Use this skill when code changes imply documentation changes.

## Workflow

1. Identify behavior, route, command, or workflow changes in scope.
2. Find the source-of-truth docs for those surfaces — use `docs/maps/docs-map.md` ("Goes stale when" column) to map changed code to owning documentation files.
3. Apply targeted documentation updates.
4. Flag missing docs when documentation should exist but does not.

## Constraints

- Do not rewrite docs broadly when a focused update is enough.
- Do not change runtime behavior while syncing docs.
- Do not leave code examples stale after command or route changes.

## Repo references

- `docs/architecture/nav-guide.md` — task → file lookup; start here to locate affected files
- `docs/maps/docs-map.md` — maps code surfaces to owning documentation files
- `README.md` files across the repo
- `python -m scripts.checks.readme_check`

## Expected output

1. Impacted docs
2. Exact updates made
3. Remaining drift or follow-up items
