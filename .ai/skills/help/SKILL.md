---
name: help
description: Lists all available agents, skills, and common prompts for this repository. Use when asked what skills or agents are available, how to invoke a skill, what a skill does, or to get a summary of the project's AI tooling. Triggered by "/help", "what skills are available", "list agents", "what can you do", or similar discovery requests.
invoker: any
---

# Help — Available Agents and Skills

Read the files listed under Repo references, then format the response using the template below. Do not summarize from memory — read the current files so the output reflects the actual state of the repository.

## Response template

```
## Agents

Agents are specialized Claude sessions scoped to a subsystem. Invoke with `@<agent-name> <task>`.

| Agent | When to use | Invoke with |
|---|---|---|
| <name> | <description one-liner> | `@<slug> <hint>` |
...

---

## Skills

Skills are reusable workflows invoked by name. Type the trigger phrase or slash command.

| Skill | When to use | Invoke with | Who can invoke |
|---|---|---|---|
| <name> | <description one-liner> | `/<name>` or natural phrase | <invoker value> |
...

---

## Common Prompts

Shortcuts for frequent tasks:

| What you want | Say |
|---|---|
| Run all checks before a commit | "validate" or "run checks" |
| Review the current diff | "review" or "code review" |
| Check if a PR is ready | "pr ready" |
| Add tests for a module | "expand tests for <path>" |
| Sync docs after a code change | "sync docs" or "update docs" |
| Create a schema migration | "@db-migration-steward <change description>" |
| Explain a financial concept | "finance: <concept>" |
| Create a reference doc or ADR | "reference doc: <topic>" |

---

## Where to go next

- `docs/architecture/nav-guide.md` — task → file lookup (start here for any code change)
- `docs/maps/docs-map.md` — which docs to update after a change
- `docs/reference/skill-invocation-policy.md` — who can invoke which skill and why
```

## Formatting rules

- Pull agent names and descriptions from the `name` and `description` frontmatter fields in `bots/agents/*.agent.md`.
- Pull skill names, descriptions, and invoker values from the `name`, `description`, and `invoker` frontmatter fields in `bots/skills/*/SKILL.md`.
- For the "Invoke with" column: use the agent's `argument-hint` to derive a short example; for skills, use `/<name>` as the primary trigger.
- For "Who can invoke": render `any` as "Anyone", `human` as "Human only", `agent:<name>` as "**<Agent Display Name>** agent only".
- Keep descriptions to one line. Do not copy full frontmatter descriptions verbatim — trim to the core WHAT.

## Repo references

- `bots/agents/backtesting-analyst.agent.md`
- `bots/agents/broker-live-safety.agent.md`
- `bots/agents/db-migration-steward.agent.md`
- `bots/agents/trading-runtime.agent.md`
- `bots/skills/check-pr-readiness/SKILL.md`
- `bots/skills/code-review/SKILL.md`
- `bots/skills/create-memory/SKILL.md`
- `bots/skills/create-skill/SKILL.md`
- `bots/skills/db-migration/SKILL.md`
- `bots/skills/expand-tests/SKILL.md`
- `bots/skills/finance-strategy/SKILL.md`
- `bots/skills/help/SKILL.md`
- `bots/skills/reference-doc/SKILL.md`
- `bots/skills/update-documentation/SKILL.md`
- `bots/skills/update-skill/SKILL.md`
- `bots/skills/validate-code/SKILL.md`
- `docs/reference/skill-invocation-policy.md`
