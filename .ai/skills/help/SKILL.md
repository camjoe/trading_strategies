---
name: help
description: Lists all available skills and common prompts for this repository. Use when asked what skills are available, how to invoke a skill, what a skill does, or to get a summary of the project's AI tooling. Triggered by "/help", "what skills are available", "what can you do", or similar discovery requests.
---

# Help — Available Skills

Read the files listed under Repo references, then format the response using the template below. Do not summarize from memory — read the current files so the output reflects the actual state of the repository.

## Response template

```
## Skills

Skills are reusable workflows invoked by name. Type the trigger phrase or slash command.

| Skill | When to use | Invoke with |
|---|---|---|
| <name> | <description one-liner> | `/<name>` or natural phrase |
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
| Create a schema migration | "migrate: <change description>" (db-migration skill) |
| Explain a financial concept | "finance: <concept>" |
| Create a reference doc or ADR | "reference doc: <topic>" |

---

## Where to go next

- `docs/architecture/nav-guide.md` — task → file lookup (start here for any code change)
- `docs/maps/docs-map.md` — which docs to update after a change
```

## Formatting rules

- Pull skill names and descriptions from the `name` and `description` frontmatter fields in `.ai/skills/*/SKILL.md`.
- For the "Invoke with" column: use `/<name>` as the primary trigger, plus a natural phrase from the description.
- Keep descriptions to one line. Do not copy full frontmatter descriptions verbatim — trim to the core WHAT.

## Repo references

Do **not** work from a hard-coded file list (it drifts). Enumerate the current inventory from disk:

- Skills: every `.ai/skills/*/SKILL.md`
