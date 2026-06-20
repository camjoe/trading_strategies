# Reference Doc Standard

Type: convention
Status: Active
Created: 2026-06-13
Last Reviewed: 2026-06-16
Purpose: Define the standard header format and document types for files under docs/reference/.
Related: [Doc Header Standard](doc-header.md), [README Layout Standard](readme-layout.md)

## Purpose

Define the standard header format and document types for all files under `docs/reference/`. This keeps reference material consistent and scannable for both human contributors and AI agents.

---

## Document Types

Two types are used in `docs/reference/`:

| Type | Purpose | Naming |
|---|---|---|
| `notes` | Living reference material — how something works, current state, usage patterns | `notes-<topic>.md` |
| `adr` | Architecture Decision Record — a decision made, its context, and rationale | `adr-<topic>.md` |

### Notes

Living documents. Updated as the code evolves. Use for:
- How a system works (migration system, broker integration, backtesting)
- Current-state audits (schema usage, strategy catalog)
- Operational recipes and usage patterns

### ADR

Decision records. Once accepted, the `Status` and `Date` fields should not change — supersede with a new ADR instead. Use for:
- Architecture decisions with non-obvious rationale
- Choices where alternatives were considered
- Decisions that constrain future work

---

## Required Header Fields

Every file in `docs/reference/` must start with the following metadata block, immediately after the `# Title` line:

### Notes header

```
Type: notes
Status: Active | Draft | Deprecated
Created: YYYY-MM-DD
Last Reviewed: YYYY-MM-DD
```

**Status values:**
- `Active` — current and maintained
- `Draft` — work in progress, not yet authoritative
- `Deprecated` — superseded or no longer relevant; leave in place for history with a note pointing to the replacement

### ADR header

```
Type: adr
Status: Proposed | Accepted | Superseded
Date: YYYY-MM-DD
Superseded By: <filename> (only when Status: Superseded)
```

**Status values:**
- `Proposed` — under discussion
- `Accepted` — decision finalized and in effect
- `Superseded` — replaced by a newer decision; always add `Superseded By:` pointing to the replacement file

---

## Recommended Section Layout

### Notes

1. `## Purpose` — what this document is and who should read it
2. `## Overview` or `## How It Works` — current-state description
3. `## Usage` or `## Commands` — operational recipes (if applicable)
4. `## Boundaries` or `## Constraints` — rules that govern the area
5. `## Related Docs` — links to adjacent reference material

### ADR

1. `## Context` — what problem existed and what alternatives were considered
2. `## Decision` — what was decided and how it works
3. `## Consequences` — trade-offs, constraints imposed, follow-up work

---

## Authoring Checklist

Before finalizing a new or updated reference doc:

1. ✅ File name follows `notes-<topic>.md` or `adr-<topic>.md` pattern
2. ✅ Header block is complete with all required fields
3. ✅ `Last Reviewed` date updated when making substantive changes (notes only)
4. ✅ Link added to `docs/README.md` reference section if it's a new file
5. ✅ For a new ADR: link added from any affected architecture doc

To create a new reference doc in the correct format, use the `reference-doc` skill (`.ai/skills/reference-doc/SKILL.md`) or copy the relevant template from `docs/reference/TEMPLATE.notes.md` or `docs/adr/TEMPLATE.adr.md`.

---

## Related

- Templates: `docs/reference/TEMPLATE.notes.md`, `docs/adr/TEMPLATE.adr.md`
- Skill: `.ai/skills/reference-doc/SKILL.md`
- README layout standard (for README files, not reference docs): `docs/reference/readme-layout.md`

