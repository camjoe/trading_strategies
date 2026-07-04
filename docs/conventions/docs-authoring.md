# Documentation Authoring Standard

Type: convention
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-02
Purpose: Define the required metadata header, document types, templates, and reference/ADR layouts for docs/ files.
Related: [README Layout Standard](readme-layout.md), [File Naming Convention](naming.md), [Docs Map](../maps/docs-map.md)

## Header Format

Every non-template file under `docs/` gets this metadata block immediately after the H1 title:

```markdown
# Title

Type: <doc-type>
Status: <status>
Created: YYYY-MM-DD
Last Reviewed: YYYY-MM-DD
Purpose: One sentence describing what this doc is for.
Related: [Name](relative/path.md), [Name](relative/path.md)
```

Allowed `Type` and `Status` values live in `scripts/checks/docs/doc_header_check.py`; the CI profile
enforces them. A status may include a parenthetical or dash suffix after a valid leading token
(for example, `Ready (multi-commit)`).

---

## Field Rules

**`Type`** — pick the closest match from the vocabulary above. If a file spans two types, choose the primary intent.

**`Status`** — `Active` is the default for any finished, accurate doc. Use `Draft` while a doc is incomplete. ADRs use `Proposed` → `Accepted` (or `Superseded` if reversed).

**`Created`** — the date the file was first written. Set once; never update.

**`Last Reviewed`** — update whenever you verify the content is still accurate, not just when you make edits. A review with no changes is still worth recording.

**`Purpose`** — one sentence, written so someone can decide whether to read the doc without opening it. Should answer: "what does this doc tell me, and why would I reach for it?"

**`Related`** — comma-separated inline markdown links to directly connected docs (e.g. an ADR links to the notes it affects; a runbook links to the script it operates). Omit the line entirely if there are no meaningful related docs — don't leave it blank.

---

## Templates

`TEMPLATE.adr.md` and `TEMPLATE.notes.md` use placeholder values and are skipped by the header
checker. When creating a new file from a template, fill in the metadata block before writing body
content.

---

## Reference docs and ADRs — section layouts

(Absorbed from the former `conventions/reference-doc.md`; this file is the single standard.)

**Reference notes** (`Type: notes`, in `docs/reference/`) are living documents updated as the code
evolves — subsystem deep-dives, current-state audits, operational recipes. Recommended layout:

1. `## Purpose` — what this document is and who should read it
2. `## Overview` or `## How It Works` — current-state description
3. `## Usage` or `## Commands` — operational recipes (if applicable)
4. `## Boundaries` or `## Constraints` — rules that govern the area
5. `## Related Docs` — links to adjacent reference material

**ADRs** (`Type: adr`, in `docs/adr/`, `NNN-` numbered per [naming.md](naming.md)) record a decision,
its context, and rationale. Once `Accepted`, don't edit the decision content — supersede with a new
ADR (set `Status: Superseded` on the old one and link the replacement in `Related`). Layout:

1. `## Context` — what problem existed and what alternatives were considered
2. `## Decision` — what was decided and how it works
3. `## Consequences` — trade-offs, constraints imposed, follow-up work

Use the `reference-doc` skill (`.ai/skills/reference-doc/SKILL.md`) or copy
`docs/reference/TEMPLATE.notes.md` / `docs/adr/TEMPLATE.adr.md`.

---

## Scope

All files under `docs/` follow this standard, with `TEMPLATE.*.md` as placeholder-only templates.

**Enforcement:** `python -m scripts.checks.docs.doc_header_check --enforce` verifies the required fields
and Type/Status vocabulary across `docs/` in the CI profile.
