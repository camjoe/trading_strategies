# Skill Invocation Policy

Type: policy
Status: Active
Created: 2026-06-13
Last Reviewed: 2026-06-16
Purpose: Define who is allowed to invoke each skill and how that restriction is declared and enforced via the invoker field.
Related: [Agent Skills Reference](agent-skills.md)

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
| `any` | Any human user or agent may invoke this skill directly |
| `human` | Human users only — agents should not invoke this skill on their own |
| `agent:<agent-name>` | Only the named agent may invoke this skill; human users must route through that agent |

`<agent-name>` matches the `name` field in the agent's `.agent.md` frontmatter, lowercased and hyphenated (e.g. `agent:db-migration-steward`).

---

## How Enforcement Works

Enforcement is **convention-based**: restricted skills include a standard preamble at the top of their body that instructs Claude to check invoker context and refuse if the restriction is not met.

Claude determines invoker context from its active system prompt:
- If Claude is operating under an `.agent.md` system prompt, it is acting as that agent.
- If Claude is operating in a general session with a human user, the invoker is `human`.

### Enforcement preamble (for `invoker: agent:<name>` skills)

Restricted skills place this block immediately after the title, before any workflow content:

```markdown
## Invocation Check

This skill is restricted to the **<Agent Display Name>** agent.

- If you are the <Agent Display Name> agent, proceed with the workflow below.
- If you are a human user or a different agent, **stop** and respond:

  > "This skill is restricted to the **<Agent Display Name>** agent. To proceed safely, invoke the agent instead:
  > `@<agent-shortcut> <your task description>`
  > The agent will use this skill to complete the task within its safety guardrails."

Do not execute any workflow steps below until the invoker check passes.
```

---

## Current Skill Roster

| Skill | `invoker` | Rationale |
|---|---|---|
| `check-pr-readiness` | `any` | General workflow tool |
| `code-review` | `any` | General review tool |
| `create-memory` | `any` | Reference doc authoring |
| `create-skill` | `any` | Skill authoring |
| `db-migration` | `agent:db-migration-steward` | Schema changes carry production risk; the steward agent enforces additive-only rules and backup hygiene |
| `expand-tests` | `any` | General testing tool |
| `finance-strategy` | `any` | Domain knowledge, no side effects |
| `help` | `any` | Discovery tool |
| `reference-doc` | `any` | Documentation authoring |
| `update-documentation` | `any` | Documentation maintenance |
| `update-skill` | `any` | Skill maintenance |
| `validate-code` | `any` | Deterministic checks, no side effects |

---

## Adding a New Restriction

1. Set `invoker: agent:<agent-name>` in the skill's frontmatter.
2. Add the enforcement preamble (template above) at the top of the skill body.
3. Update the roster table in this document.
4. Update the `docs/maps/skills-map.md` "Who can invoke" column.

## Removing a Restriction

1. Change `invoker` back to `any`.
2. Remove the enforcement preamble from the skill body.
3. Update the roster table and skills-map.

---

## Related References

- `docs/maps/skills-map.md` — full discovery index of agents and skills
- `bots/skills/help/SKILL.md` — `/help` skill for interactive discovery
- `bots/agents/` — agent definitions
- `bots/skills/` — skill definitions
