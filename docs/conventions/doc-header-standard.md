# Doc Header Standard

Type: convention
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-06-16
Purpose: Define the required metadata header for every file under docs/ so files are self-describing for both developers and agents.
Related: [Reference Doc Standard](reference-doc-standard.md), [README Layout Standard](readme-layout-standard.md), [Docs Map](../maps/docs-map.md)

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
Related: [Burn-In Protocol](burn_in_protocol.md), [Governance Review Guide](governance_review_guide.md)
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

---

## Status Vocabulary

| Status | Meaning |
|---|---|
| `Active` | Current and accurate |
| `Draft` | Being written, not yet authoritative |
| `Proposed` | ADR under discussion |
| `Accepted` | ADR decision finalized |
| `Superseded` | Replaced by another doc — link the replacement in `Related` |

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

## Scope

All files under `docs/` follow this standard. The one exception is `docs/reference/notes-agent-skills.md`, which is a copy of external upstream documentation and is intentionally not owned by this project.
