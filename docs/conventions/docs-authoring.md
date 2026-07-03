# Documentation Authoring Standard

Type: convention
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-02
Purpose: Define the required metadata header, document types, templates, and reference/ADR layouts for docs/ files.
Related: [README Layout Standard](readme-layout.md), [File Naming Convention](naming.md), [Docs Map](../maps/docs-map.md)

## Header Format

Every file under `docs/` gets this block immediately after the H1 title:

```markdown
# Title

Type: <doc-type>
Status: <status>
Created: YYYY-MM-DD
Last Reviewed: YYYY-MM-DD
Purpose: One sentence describing what this doc is for.
Related: [Name](relative/path.md), [Name](relative/path.md)
```

Example:

```markdown
# Daily Operations Runbook

Type: runbook
Status: Active
Created: 2026-03-15
Last Reviewed: 2026-06-16
Purpose: Procedures for monitoring and recovering the daily IBKR Paper Autonomy workflow.
Related: [Burn-In Protocol](burn-in-protocol.md), [Governance Review Guide](governance-review.md)
```

---

## Type Vocabulary

| Type | Used for |
|---|---|
| `index` | Navigation/index files (`README.md`, `runbooks/README.md`) |
| `map` | File/directory inventory maps |
| `architecture` | Layer design, service boundaries, task-to-file lookup |
| `runbook` | Step-by-step operational procedures |
| `notes` | Living reference — subsystem deep-dives, schema audits |
| `adr` | Architecture Decision Records |
| `convention` | Coding or doc standards (style, naming, headers) |
| `template` | Blank starter files |
| `policy` | Access control, invocation rules |
| `overview` | The top-level app explainer (entry point) |
| `plan` | Task/priority trackers and living plans |
| `spec` | Target-state design specs (e.g. schema targets) |
| `implementation` | Per-initiative work orders in `docs/implementation/` |

---

## Status Vocabulary

| Status | Meaning |
|---|---|
| `Active` | Current and accurate |
| `Draft` | Being written, not yet authoritative |
| `Ready` | Work order ready to execute (implementation guides) |
| `Complete` | Finished work retained for the record |
| `Proposed` | ADR under discussion |
| `Accepted` | ADR decision finalized |
| `Superseded` | Replaced by another doc — link the replacement in `Related` |

The status is the leading token; a parenthetical or dash suffix may add context (e.g.
`Ready (multi-commit)`, `Complete (foundation phase)`).

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

`TEMPLATE.adr.md` and `TEMPLATE.notes.md` use placeholder values. When creating a new file from a template, fill in all six fields before writing any content.

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

**Authoring checklist** (new or updated reference doc / ADR):

1. ✅ File name follows [naming.md](naming.md) (plain kebab-case in `reference/`; `NNN-<topic>.md` in `adr/`)
2. ✅ Header block complete (six fields above); `Last Reviewed` updated on substantive changes
3. ✅ Linked from `docs/README.md` (and `docs/maps/docs-map.md`) if it's a new file
4. ✅ For a new ADR: linked from any affected architecture doc

Use the `reference-doc` skill (`.ai/skills/reference-doc/SKILL.md`) or copy
`docs/reference/TEMPLATE.notes.md` / `docs/adr/TEMPLATE.adr.md`.

---

## Scope

All files under `docs/` follow this standard, with no exceptions (`TEMPLATE.*.md` files hold
placeholder values and are skipped by tooling).

**Enforcement:** `python -m scripts.checks.doc_header_check` verifies the required fields and
Type/Status vocabulary across `docs/` (advisory; runs in the CI profile). Keep this file's
vocabulary tables and the check's vocabulary in sync when adding a type or status.
