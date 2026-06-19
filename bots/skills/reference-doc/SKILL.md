---
name: reference-doc
description: Captures reusable patterns, reference documents, and architectural decisions as persistent knowledge artifacts. Use when asked to create a reference doc, ADR, or any structured knowledge artifact for this repository.
invoker: any
---

# Reference Doc

## Choose a task

| Task | Use when | Reference |
|---|---|---|
| Reference doc or ADR | Documenting an architectural decision, reference material, or team convention | [reference-doc.md](reference-doc.md) |

## Workflow

1. Determine the artifact type: `notes` (living reference) or `adr` (decision record).
2. Follow the standard in [reference-doc.md](reference-doc.md) for header format, section layout, and file naming.
3. Place the new file in `docs/reference/`.
4. Link it from `docs/README.md`.
5. Cross-link from any affected architecture doc if this is an ADR.

## Constraints

- Do not invent content — only document what is already true or decided.
- Use the exact header format from `docs/reference/reference-doc.md`.
- For ADRs: once accepted, do not change the decision body. Create a superseding ADR instead.

## Repo references

- `docs/reference/reference-doc.md`
- `docs/reference/TEMPLATE.notes.md`
- `docs/adr/TEMPLATE.adr.md`
- `docs/README.md`
