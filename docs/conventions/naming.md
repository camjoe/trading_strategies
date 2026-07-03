# File Naming Convention

Type: convention
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-02
Purpose: Define how documentation files and folders are named so paths are predictable for both developers and agents.
Related: [Documentation Authoring Standard](docs-authoring.md), [Docs Map](../maps/docs-map.md)

## Case

Use **`kebab-case.md`** for all files and folders: lowercase, words separated by single hyphens. No `snake_case`, no `SCREAMING_SNAKE`, no spaces.

- ✅ `service-cookbook.md`, `broker-integration.md`, `burn-in-protocol.md`
- ❌ `service_cookbook.md`, `BrokerIntegration.md`, `burn in protocol.md`

## Reserved names (kept UPPERCASE)

These are mandated by tooling or universal convention and are the only exceptions to kebab-case:

`README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SKILL.md`, and `TEMPLATE.*.md`.

## The folder conveys the type — don't repeat it in the name

A file's folder already says what kind of doc it is, so don't restate it in the filename.

| Folder | Don't write | Write | Rule |
|---|---|---|---|
| `reference/` | `notes-backtesting.md` | `backtesting.md` | no `notes-` prefix |
| `conventions/` | `docs-authoring-standard.md` | `docs-authoring.md` | no `-standard` / `-guide` / `-convention` suffix |
| `conventions/` | `python-general-style.md` | `python-style.md` | same |
| `runbooks/` | `governance-review-guide.md` | `governance-review.md` | a runbook is already a procedure; no `-guide` |

## ADRs are numbered

Files in `adr/` use a **three-digit sequential prefix**: `NNN-title.md`.

- `001-cross-platform-paths.md`, `002-backtesting-layering.md`, `003-sleeve-virtualization-architecture.md`
- The number reflects **acceptance order** and never changes once assigned — it gives a stable `ADR-NNN` id you can cite from other docs even if the title is later edited.
- Assign the next unused number when adding an ADR.

## Meaningful suffixes that are kept

Some suffixes carry information tooling reads — keep these:

- `TEMPLATE.*.md` — blank starter files (e.g. `TEMPLATE.adr.md`, `TEMPLATE.notes.md`).

## Quick test

Before naming a file, ask: *"Does any part of this name repeat what the folder already tells me?"* If yes, drop that part. The exceptions above (reserved names, ADR numbers, tool-read suffixes) are the only information worth keeping that the folder doesn't already provide.
