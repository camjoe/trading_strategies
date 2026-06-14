---
name: update-documentation
description: Syncs READMEs, architecture notes, API docs, and operational documentation with code changes. Use when code changes imply documentation drift, when asked to sync docs, or when a README or doc is stale.
---

# Update Documentation

## Modes

| Mode | Use when | Reference |
|---|---|---|
| Docs sync | Code changes imply doc updates | [docs-sync.md](docs-sync.md) |
| Docs check | Pre-PR passive staleness check | [docs-check.md](docs-check.md) |

**Docs sync** — active: identify changed surfaces, find owning docs, apply targeted updates.
**Docs check** — passive: run `readme_check`, scan diff for stale paths/commands. Advisory only; never blocks.

## Constraints

- Do not rewrite docs broadly when a focused update is enough.
- Do not change runtime behavior while syncing docs.
- Do not leave code examples stale after command or route changes.

## Creating reference docs or ADRs?

Use the `reference-doc/` skill instead — it handles new reference documents and architecture decision records.

## Repo references

- `AGENTS.md`
- `.github/DOCS_PRECOMMIT_POLICY.md`
- `README.md` files across the repo
