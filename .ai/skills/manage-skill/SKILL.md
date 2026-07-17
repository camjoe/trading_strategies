---
name: manage-skill
description: Creates, improves, or refactors SKILL.md files in .ai/skills. Use when asked to create a new skill, update an existing skill, fix skill triggering, reduce skill verbosity, or restructure skill references.
---

# Manage Skill

## Choose the workflow

- Creating a new reusable task surface: follow `Creating a skill`.
- Improving an existing skill: follow `Updating a skill`.

## Creating a skill

1. **Identify the gap** — what repeatable task needs durable context?
2. **Choose a directory name** — lowercase, hyphenated, gerund-style when natural: `reviewing-code`, `validating-pr`, `processing-data`.
3. **Write the frontmatter**
   - `name`: gerund phrase, max 64 chars.
   - `description`: third person, WHAT + WHEN, specific trigger terms, max 1024 chars.
4. **Write the body** — concise workflow steps, constraints, and output template. Keep `SKILL.md` under 500 lines.
5. **Add sibling reference files only when needed** for domain detail loaded on demand.
6. **Place the entry point in** `.ai/skills/<skill-name>/SKILL.md`.

## Updating a skill

1. **Read the current skill** — understand its intent, existing instructions, and structure.
2. **Identify the problem** — what is failing or suboptimal?
   - Not triggering: fix `description` with a clear WHEN clause and user-facing trigger terms.
   - Triggering too broadly: narrow `description`.
   - Producing poor output: clarify steps, constraints, or expected output.
   - Too verbose: split detail into sibling reference files or cut context the model already has.
   - Wrong structure: promote or demote content between `SKILL.md` and reference files.
3. **Apply the smallest useful fix**. Do not rewrite a working skill without an observed failure case.
4. **Verify against the quality checklist**.

## Layout rules

Skills live as folder-based entries:

```text
.ai/skills/
└── <skill-name>/
    ├── SKILL.md
    └── <reference>.md
```

- `SKILL.md` is the only skill entry point.
- Sibling `.md` files are reference files loaded on demand by `SKILL.md`; they are not skills.
- Single-file skills are the norm when the workflow fits in one page.
- Do not maintain a hand-written reference-file inventory; each `SKILL.md` should link only the references it may load.
- Do not use nested reference chains; all references must be one level deep from `SKILL.md`.
- Do not reintroduce retired flat `.skill.md` shims, blank skill templates, or retired standalone skills without a fresh decision.

## Frontmatter rules

```yaml
---
name: doing-something
description: Does X and Y. Use when Z or when the user asks about W.
---
```

- Use third person: "Reviews code changes", not "I can review" or "Use this to review".
- Include both WHAT and WHEN; discovery depends on `description`.
- Include specific words users will actually say.

## Body guidance

Use this shape when the skill needs a clear output contract:

```markdown
## Workflow
1. Step one
2. Step two

## Constraints
- Do not X
- Do not Y

## Repo references
- path/to/relevant/file

## Expected output
1. Output section 1
2. Output section 2
```

Match instruction detail to task fragility:

| Task type | Freedom level | Use |
|---|---|---|
| Context-dependent, many valid approaches | High | Natural language steps |
| Preferred pattern with some variation | Medium | Template with parameters |
| Fragile, exact sequence required | Low | Exact commands, no variation |

## Localization boundaries

- Keep skills reusable in a similar repo with light localization.
- Do not assume this repo's layout is universal.
- Do not present repo-specific commands as if they exist everywhere.
- Keep project-only safety rules in `AGENTS.md` or architecture docs, not inside reusable skills.

## Quality checklist

- [ ] Description is third-person and includes both WHAT and WHEN.
- [ ] Body is under 500 lines.
- [ ] No time-sensitive information.
- [ ] Consistent terminology throughout.
- [ ] References are one level deep from `SKILL.md`.
- [ ] Workflow has numbered steps.
- [ ] Output template is present if output format matters.
- [ ] File paths use forward slashes.

## Repo references

- `AGENTS.md` — repo routing guide and current skill inventory.
- `.ai/skills/` — existing skills for reference and consistency.
