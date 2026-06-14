---
name: update-documentation
description: Syncs READMEs, architecture notes, API docs, and operational documentation with code changes. Use when code changes imply documentation drift, when asked to sync docs, or when a README or doc is stale.
---

# Update Documentation

## Workflow

Follow [docs-sync.md](docs-sync.md) for all documentation drift work.

1. Identify behavior, route, command, or workflow changes in scope.
2. Find the source-of-truth docs for those surfaces.
3. Apply targeted documentation updates.
4. Flag missing docs when documentation should exist but does not.
5. Run `python -m scripts.checks.readme_check` after edits.

## Constraints

- Do not rewrite docs broadly when a focused update is enough.
- Do not change runtime behavior while syncing docs.
- Do not leave code examples stale after command or route changes.

## Creating reference docs or ADRs?

Use the `create-memory/` skill instead — it handles new reference documents and architecture decision records.

## Repo references

- `AGENTS.md`
- `.github/DOCS_PRECOMMIT_POLICY.md`
- `README.md` files across the repo
