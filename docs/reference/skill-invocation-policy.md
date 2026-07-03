# Skill Invocation Policy

Type: policy
Status: Active
Created: 2026-06-13
Last Reviewed: 2026-07-02
Purpose: Define who is allowed to invoke each skill and how that restriction is declared and enforced via the invoker field.
Related: [AGENTS.md](../../AGENTS.md), [AI Index](../../.ai/README.md)

Defines who is allowed to invoke each skill and how that restriction is declared and enforced.

---

## Invoker Field

Every skill's `SKILL.md` frontmatter declares an `invoker` field:

```yaml
---
name: skill-name
description: ...
invoker: any          # anyone may invoke this skill
---
```

### Allowed values

| Value | Meaning |
|---|---|
| `any` | Any human user or AI session may invoke this skill directly |
| `human` | Human users only — AI sessions should not invoke this skill on their own |

Historical note: an `agent:<name>` value existed while the repo had agent personas; the
agents were retired 2026-07-02 and the value with them. The safety rules those restrictions
protected (additive-only migrations, backup hygiene, the live-trading guard) live in the skills
themselves and in `docs/architecture/architecture-conventions.md`, and apply to every session.

## How Enforcement Works

Enforcement is **convention-based**: a restricted skill states its restriction in a short preamble
at the top of its body, instructing the model to check invoker context and refuse if unmet.

## Current Skill Roster

All skills are currently `invoker: any` — none are restricted. The roster is the `invoker`
frontmatter across `.ai/skills/*/SKILL.md`; the frontmatter is the source of truth.

## Adding a Restriction

1. Set `invoker: human` in the skill's frontmatter.
2. Add a short refusal preamble at the top of the skill body.
3. Update the `AGENTS.md` routing guide if the restriction changes how the skill is routed.

---

## Related References

- `AGENTS.md` — routing guide for skills
- `.ai/skills/` — skill definitions (frontmatter is the invoker source of truth)
