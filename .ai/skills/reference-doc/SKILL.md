---
name: reference-doc
description: Captures reusable patterns, reference documents, and architectural decisions as persistent knowledge artifacts. Use when asked to create a reference doc, ADR, or any structured knowledge artifact for this repository.
---

# Reference Doc

Create a new reference document in `docs/reference/` or an ADR in `docs/adr/`, or update an
existing one to meet the standard. The authoritative header format, section layouts, and
authoring checklist live in `docs/conventions/docs-authoring.md` — follow that file; this skill
is the workflow around it.

## Workflow

1. **Determine type** — `notes` (living reference material, `docs/reference/<kebab-topic>.md`)
   or `adr` (decision record, `docs/adr/NNN-<kebab-topic>.md`, next unused number).
2. **Copy the template** — `docs/reference/TEMPLATE.notes.md` or `docs/adr/TEMPLATE.adr.md` —
   and fill every header field per `docs/conventions/docs-authoring.md`.
3. **Draft sections** — follow the section layout for the doc type in docs-authoring.md.
4. **Link the new doc** — add an entry to `docs/README.md` (and `docs/maps/docs-map.md`).
5. **Cross-link** — for an ADR, add a reference from the affected architecture doc
   (e.g. `docs/architecture/architecture-conventions.md`).

## Constraints

- Do not invent content — only document what is already true or decided.
- Do not leave placeholder header values (`YYYY-MM-DD`) unfilled; `Last Reviewed` is the date the
  content was verified accurate, not merely touched.
- For ADRs: once `Status: Accepted`, do not change the decision body — supersede with a new ADR.

## Repo references

- `docs/conventions/docs-authoring.md` — authoritative header standard, layouts, and checklist
- `docs/reference/TEMPLATE.notes.md` / `docs/adr/TEMPLATE.adr.md` — templates
- `docs/README.md` — reference section to update after creating a new doc

## Expected output

1. New or updated file in `docs/reference/` or `docs/adr/`
2. Updated `docs/README.md` (and docs-map) entries
3. Cross-link added to any affected architecture doc (ADRs only)
4. All required header fields present and valid
