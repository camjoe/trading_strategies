---
name: reference-doc
description: Create or update a reference doc or ADR in docs/reference/ using the standard header format and section layout for this repository.
---

# Reference Doc

Use this skill to create a new reference document (`notes-*.md`) or Architecture Decision Record (`adr-*.md`) in `docs/reference/`, or to update an existing one to meet the standard.

## Workflow

1. **Determine type** — `notes` for living reference material; `adr` for a decision record.
2. **Choose a filename** — `notes-<kebab-topic>.md` or `adr-<kebab-topic>.md`.
3. **Fill the header block** — all required fields as defined in `docs/conventions/docs-authoring.md`.
4. **Draft sections** — follow the recommended section layout for the doc type.
5. **Apply content** — write the document with concrete, actionable content.
6. **Link the new doc** — add an entry to `docs/README.md` under "Reference Notes and ADRs".
7. **Cross-link** — if the doc is an ADR, add a reference from the affected architecture doc (e.g., `docs/architecture/architecture-conventions.md`).

## Header formats

### Notes

```
Type: notes
Status: Active | Draft | Deprecated
Created: YYYY-MM-DD
Last Reviewed: YYYY-MM-DD
```

### ADR

```
Type: adr
Status: Proposed | Accepted | Superseded
Date: YYYY-MM-DD
Superseded By: <filename>  (only when Status: Superseded)
```

## Section layout

### Notes sections

1. `## Purpose` — what this doc is and who should read it
2. `## Overview` or `## How It Works`
3. `## Usage` or `## Commands` (if applicable)
4. `## Boundaries` or `## Constraints`
5. `## Related Docs`

### ADR sections

1. `## Context` — problem statement and alternatives considered
2. `## Decision` — what was decided and how it works
3. `## Consequences` — trade-offs and follow-up constraints

## Constraints

- Do not invent content — only document what is already true or decided.
- Do not omit the header block or leave placeholder values like `YYYY-MM-DD` unfilled.
- `Last Reviewed` should be the date the content was last verified as accurate, not just the date the file was touched.
- For ADRs: once `Status: Accepted`, do not change the decision body — create a new superseding ADR instead.

## Repo references

- `docs/conventions/docs-authoring.md` — authoritative header standard and section guidance
- `docs/reference/TEMPLATE.notes.md` — notes template
- `docs/adr/TEMPLATE.adr.md` — ADR template
- `docs/README.md` — reference section to update after creating a new doc

## Expected output

1. New or updated file in `docs/reference/`
2. Updated `docs/README.md` entry
3. Cross-link added to any affected architecture doc (ADRs only)
4. Confirmation that all required header fields are present and valid
