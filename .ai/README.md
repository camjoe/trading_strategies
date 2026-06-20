# AI

Type: index
Status: Active
Created: 2026-06-17
Last Reviewed: 2026-06-19
Purpose: Define the two agent surfaces (skills and agents) and when to reach for each.
Related: [AGENTS.md](../AGENTS.md), [Agent Skills Guide](../docs/reference/agent-skills.md), [Skill Invocation Policy](../docs/reference/skill-invocation-policy.md)

Operational assets for AI agents working in this repo. **[`AGENTS.md`](../AGENTS.md)** (repo root) is the canonical entrypoint and routing guide; this folder holds the capabilities it routes to.

## The two surfaces

| Surface | What it is | Reach for it when | Lives in |
|---|---|---|---|
| **Skill** | A reusable, self-contained capability with a `SKILL.md` entrypoint | the task is generic enough to recur (review, validate, migrate, expand tests) | `.ai/skills/<skill>/` |
| **Agent** | A scoped persona with repo-specific paths, safety rules, and permitted commands | a task needs project-specific execution detail or guardrails a generic skill can't carry | `.ai/agents/<name>.agent.md` |

**Rule of thumb:** prefer a **skill**; escalate to an **agent** only when repo-specific execution value matters.

## When to use which

- Default to the most specific matching skill — see the routing tables in [`AGENTS.md`](../AGENTS.md).
- Use an agent only when it adds exact repo paths, project-only safety rules, domain/workflow constraints, or operator-workflow integration.
- Authoring a new skill or agent? Use the `create-skill` skill and the [Agent Skills guide](../docs/reference/agent-skills.md); follow the invocation rules in [`skill-invocation-policy.md`](../docs/reference/skill-invocation-policy.md).

## Discoverability

The `help/` skill catalogs what's available; routing lives in `AGENTS.md`. Both should derive from each skill/agent's `description` (WHAT + WHEN) frontmatter — see the authoring rules in [`.ai/skills/README.md`](skills/README.md) — so they can't drift from what's on disk.

