# Reusable Skills Library

This folder is the repo's primary reusable task surface.

## Purpose

Define how this repository uses reusable skills, and provide guardrails for maintaining them.

## Usage

1. Choose the closest matching skill folder and follow its `SKILL.md`.
2. To add or improve a skill, see the authoring rules below.

## Active layout

```
.ai/skills/
├── <skill-name>/
│   ├── SKILL.md            ← canonical skill (loaded when skill triggers)
│   └── <reference>.md      ← reference files (loaded on demand by SKILL.md)
```

One folder per skill, lowercase hyphenated name. `SKILL.md` is the entry point. Additional `.md` files in the folder are reference documents loaded progressively as needed — they are not skills themselves.

## Current skill pack

| Skill folder | Covers |
|---|---|
| `check-pr-readiness/` | Full pre-PR workflow: validation + AI review + docs advisory + report |
| `code-review/` | All review modes: standard, baseline, aggressive, architecture, cleanup, contract, PR review |
| `create-runtime-job/` | Scaffold a new runtime job (module + test + sentinel + schedule + inventory) against the shared runner |
| `db-migration/` | Schema migration lifecycle: create, validate, estimate risk, generate rollback |
| `expand-tests/` | Coverage growth and regression-test expansion |
| `finance-strategy/` | Financial terminology, strategy classification, market mechanics, and evaluation honesty |
| `help/` | Interactive discovery: list available skills and common prompts |
| `manage-skill/` | Create, improve, or refactor skills following the skills guide |
| `reference-doc/` | Reference docs and ADRs in `docs/reference/` |
| `update-documentation/` | Docs drift sync — rewriting stale prose, descriptions, and responsibilities |
| `validate-code/` | Deterministic validation: repo checks + Python lint/type/test checks |

## Workflows vs skills

Some skills are executable workflows that orchestrate other skills and commands. For example,
`check-pr-readiness/` runs deterministic validation, invokes code-review judgment, runs advisory
docs checks, and saves a report. Keep workflow skills when ordering, stop conditions, or output
artifacts matter; keep capability skills like `validate-code/` and `code-review/` focused on one
kind of work.

### Reference files (inside skill folders, not skills themselves)

Do not maintain a file inventory here — it drifts. Each `SKILL.md` links the reference files it
loads; the folders on disk are the source of truth. A reference file exists only when its parent
`SKILL.md` links to it; single-file skills are the norm when the workflow fits in one page.

Retired from the active set (do not reintroduce without a fresh decision): the standalone
`deep-code-review`, `frontend-cleanup`, and `python-cleanup` skills (merged into `code-review/`
modes); flat `.skill.md` shims; blank `templates/`; `update-documentation/docs-sync.md` and
`reference-doc/reference-doc.md` (folded into their `SKILL.md`s, 2026-07-02).

## Authoring rules

### Reusability and structure

Skills should:

1. stay reusable in a similar repo with light localization
2. have a gerund `name` and a third-person `description` with both WHAT and WHEN
3. keep `SKILL.md` under 500 lines — move details into reference files
4. use one-level-deep references only (no chaining)

Skills should not:

1. assume this repo's layout is universal
2. present repo-specific commands as if they exist everywhere
3. absorb project-only safety rules that belong in `AGENTS.md` or `docs/architecture/architecture-conventions.md`

### Content philosophy

When writing a skill:

1. **Concise is key.** The context window is shared. Assume the model is already smart — only add
   context it doesn't have. Every SKILL.md paragraph must justify its token cost.
2. **Progressive disclosure.** Keep SKILL.md as the entry point; push mode- or domain-specific
   detail into sibling reference files loaded on demand.
3. **Match freedom to fragility.** Give text instructions for judgment tasks; give exact commands
   or scripts for fragile, deterministic steps (validation commands, file paths).
4. **Test with real usage.** A skill's description decides whether it triggers — write it from the
   user's task vocabulary, not the skill's internals, and iterate on real invocations.

## When to add a new skill

Add a new skill when the capability should be reusable outside this repo with only light
localization. Repo-only safety rules and routing belong in `AGENTS.md` /
`docs/architecture/architecture-conventions.md`, not inside a skill. (The former agent-persona
surface was retired 2026-07-02 — do not reintroduce it without a fresh decision.)
