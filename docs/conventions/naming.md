# File Naming Convention

Type: convention
Status: Active
Created: 2026-06-16
Last Reviewed: 2026-07-02
Purpose: Define how documentation files and folders are named so paths are predictable for both developers and agents.
Related: [Documentation Authoring Standard](docs-authoring.md), [Docs Map](../maps/docs-map.md)

## Case

Use lowercase kebab-case for docs files. The exact filename pattern is enforced by
`scripts/checks/docs/doc_naming_check.py`.

## Reserved names (kept UPPERCASE)

These are mandated by tooling or universal convention and are the only exceptions to kebab-case:

`README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SKILL.md`, and `TEMPLATE.*.md`.

## Avoid Redundant Names

A file's folder already says what kind of doc it is, so don't restate it in the filename. Prefer
`reference/backtesting.md`, `conventions/python-style.md`, and `runbooks/governance-review.md`
over names that repeat `notes`, `standard`, `guide`, or `convention`.

## ADRs are numbered

Files in `adr/` use a three-digit prefix: `NNN-title.md`. The number is the stable `ADR-NNN` id
and never changes once assigned. Gaps are allowed when an ADR is retired or deleted; do not renumber
later ADRs to fill them.

## Enforcement

`python -m scripts.checks.docs.doc_naming_check --enforce` verifies docs filenames and ADR number
uniqueness in the CI profile.
