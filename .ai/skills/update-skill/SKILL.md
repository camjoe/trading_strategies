---
name: update-skill
description: Improves or refactors existing SKILL.md files following the agent skill authoring guide. Use when a skill is not triggering correctly, producing poor output, is too verbose, or needs to be restructured after a layout change.
invoker: any
---

# Update Skill

## Workflow

1. **Read the current skill** — understand its intent, existing instructions, and structure.
2. **Identify the problem** — what is failing or suboptimal?
   - Not triggering → fix `description` (add WHEN, improve key terms)
   - Producing poor output → add/clarify steps, tighten constraints, add output template
   - Too verbose → split content into reference files, cut explanations Claude doesn't need
   - Wrong structure → promote or demote content between SKILL.md and reference files
3. **Apply the fix** — minimum change needed. Do not rewrite the whole skill unless it's broken.
4. **Verify against the quality checklist** (see below).

## Common fixes

| Symptom | Fix |
|---|---|
| Skill never triggers | Improve description — add WHEN clause, include key trigger terms |
| Skill triggers too broadly | Narrow description — be more specific about WHEN |
| Claude ignores a constraint | Move the constraint higher, use stronger language ("MUST", "NEVER") |
| Output is inconsistent | Add an explicit output template section |
| Body is too long | Move detail into reference files, keep SKILL.md as table of contents |
| Nested reference chains | Flatten — all refs must link directly from SKILL.md |

## Layout rules

- `SKILL.md` is the only skill entry point in a skill folder.
- Sibling `.md` files are reference files loaded on demand by `SKILL.md`; they are not skills.
- Single-file skills are the norm when the workflow fits in one page.
- Do not maintain hand-written reference-file inventories; the parent `SKILL.md` links the references it may load.
- Do not reintroduce retired flat `.skill.md` shims, blank skill templates, or retired standalone skills without a fresh decision.

## Quality checklist

- [ ] Description is third-person and includes both WHAT and WHEN
- [ ] Body is under 500 lines
- [ ] No time-sensitive information
- [ ] Consistent terminology throughout
- [ ] All file references are one level deep from SKILL.md
- [ ] Workflow has numbered steps
- [ ] Output template present if output format matters
- [ ] File paths use forward slashes

## Constraints

- Make the minimum change needed to fix the observed problem.
- Do not add explanations Claude already knows.
- Do not rewrite a working skill without an observed failure case.
- Keep skills reusable in a similar repo with light localization.
- Keep project-only safety rules in `AGENTS.md` or architecture docs, not inside reusable skills.

## Repo references

- `AGENTS.md` — repo routing guide and current skill inventory
- `.ai/skills/` — existing skills for structure reference
