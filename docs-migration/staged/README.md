# Staged Files

Holding area for files we **author or edit now** that belong in the **final** structure but shouldn't be placed yet (we haven't migrated). When migration executes, grab these and drop them at their destinations.

Keep names here matching their final filename so they're easy to move. Track each one's destination below.

## Staged → destination

| Staged file | Final destination | Status | Notes |
|---|---|---|---|
| `naming.md` | `docs/conventions/naming.md` | drafted | the real naming convention (D-OPEN-7); replaces the current stub |
| `CONTRIBUTING.md` | `CONTRIBUTING.md` (repo root) | to draft | real human contributor workflow (D-OPEN-8) |
| `CLAUDE.md` | `CLAUDE.md` (repo root) | to draft | thin: `@AGENTS.md` import + link to `docs/README.md` (D-OPEN-8) |
| `copilot-instructions.md` | `.github/copilot-instructions.md` | to draft | thin redirect → AGENTS.md (D-OPEN-8) |
| `quality-gates.md` | `docs/conventions/quality-gates.md` | to draft | DoD ↔ enforcing checks (D-8 / addition A) |
| `bots-README.md` | `bots/README.md` | to draft | skill vs workflow vs agent + when-to-use (D-8 / addition B) |
| `bot-authoring.md` | `docs/conventions/bot-authoring.md` | to draft | skill/agent frontmatter schema (D-8 / addition C) |

> Add a row here whenever you stage a new file. "Final destination" uses repo-root paths (no `agentswip/` — see [D-OPEN-1](../decisions.md)).
