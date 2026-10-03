---
name: update-documentation
description: Rewrites and freshens README files, architecture notes, and operational documentation when prose or responsibilities have drifted from reality. Use when docs are stale, misleading, or incomplete — not just out-of-date by timestamp.
---

# Update Documentation

Use this skill when documentation content needs rewriting — stale descriptions, wrong responsibilities, missing sections, or prose that no longer reflects how the code actually works.

Detection (is something stale?) is handled by CI and the `check-pr-readiness` workflow. This skill picks up from there: identify what needs rewriting, then rewrite it.

## Workflow

1. **Identify scope** — use `readme_check` and `link_check` output (or the PR readiness report) to find flagged files; use `docs/maps/docs-map.md` ("Goes stale when" column) to find docs affected by code changes. Scope includes **co-located READMEs across the repo** (root, `tests/`, `scripts/`, `apps/*`, `src/*` package READMEs), not just files under `docs/` — `link_check` scans every tracked `.md` and flags backtick repo-path references that no longer resolve.
2. **Read the owning doc** — understand what it currently says and why it's stale.
3. **Apply targeted updates** — rewrite only the stale sections. Do not rewrite docs broadly when a focused update is enough.
4. **Flag missing docs** — if a new surface (service, route, script) has no documentation, note it.

## Constraints

- Do not change runtime behavior while syncing docs.
- Do not leave code examples stale after command or route changes.
- Do not rewrite style or formatting when only content needs updating.

## Creating reference docs or ADRs?

Follow `docs/conventions/docs-authoring.md` — it is the authoritative standard for new reference
documents and architecture decision records (header format, templates, section layouts, and how to
register the new doc).

## Repo references

- `docs/architecture/nav-guide.md` — start here to locate which files a task touches
- `docs/maps/docs-map.md` — maps code surfaces to owning documentation files
- `README.md` files across the repo

## Expected output

1. Impacted docs
2. Exact updates made
3. Remaining drift or follow-up items
