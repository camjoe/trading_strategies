---
name: create-skill
description: Creates new SKILL.md files in .github/skills/ following the agent skill authoring guide. Use when asked to create a new skill, when a repeatable task pattern emerges, or when a workflow should be captured for future reuse.
---

# Create Skill

## Workflow

1. **Identify the gap** — what task does Claude repeatedly need context for? What information is always manually supplied?
2. **Choose a directory name** — lowercase, hyphenated, gerund-style: `reviewing-code`, `validating-pr`, `processing-data`.
3. **Write the frontmatter**
   - `name`: gerund phrase, max 64 chars (e.g. "Creating Skills")
   - `description`: third person, WHAT + WHEN, specific key terms, max 1024 chars
4. **Write the body** — concise workflow steps, constraints, and output template. Under 500 lines.
5. **Add reference files** if needed — for domain detail that only loads on demand. One level deep only.
6. **Place in** `.github/skills/<skill-name>/SKILL.md`

## Frontmatter rules

```yaml
---
name: Doing Something          # gerund, max 64 chars
description: Does X and Y. Use when Z or when the user asks about W.  # third-person, WHAT + WHEN
---
```

- **Always third person**: "Reviews code changes" not "I can review" or "Use this to review"
- **Include both WHAT and WHEN** — Claude uses description for discovery
- **Specific key terms** — include words users will actually say

## Body structure

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

## Degrees of freedom

| Task type | Freedom level | Use |
|---|---|---|
| Context-dependent, many valid approaches | High | Natural language steps |
| Preferred pattern with some variation | Medium | Template with parameters |
| Fragile, exact sequence required | Low | Exact commands, no variation |

## Quality checklist

Before finishing a skill:
- [ ] Description is third-person and includes both WHAT and WHEN
- [ ] Body is under 500 lines
- [ ] No time-sensitive information
- [ ] Consistent terminology throughout
- [ ] References are one level deep from SKILL.md
- [ ] Workflow has numbered steps
- [ ] Output template provided (if output format matters)
- [ ] File paths use forward slashes

## Repo references

- `docs/Agent Skills.md` — authoritative authoring guide
- `.github/skills/` — existing skills for reference and consistency
