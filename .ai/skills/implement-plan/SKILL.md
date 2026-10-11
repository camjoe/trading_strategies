---
name: implement-plan
description: Implements a plan from plan/ on its own branch: reads the plan, follows the repository's conventions, commits in logical steps with tests, and records anything unclear as a question instead of guessing. Use when asked to implement a plan, or when the plan pickup starts a run.
---

# Implementing a Plan

Turns one plan in `plan/` into commits on a branch. It builds; it never reviews its own work and never
decides what the plan left open. The plan pickup (`python -m scripts.forge implement-plan`) claims the
plan, opens the draft pull request, and decides afterwards whether it leaves draft.

## Invocation

```
implement plan: <file>        # plan/<file>, run in this session
```

Unattended, the owner runs `python -m scripts.forge implement-plan --plan plan/<file>`, which prepares
everything below and then starts this skill in a headless session.

## Before you start

The controller has already: confirmed the plan is listed in the index and not in progress; confirmed its
dependencies (`--depends-ok`); created the branch off `develop`; committed the claim (the plan's Status
line and its index row); pushed it; and opened a **draft** pull request. Do not redo any of it.

## Step 1 — Read

1. Read the whole plan. Treat anything it marks **unverified** or "not checked" as unverified: verify it
   before you build on it, or write it as a question.
2. Read `AGENTS.md`. Before editing anything under `src/trading/`, read
   `docs/architecture/architecture-conventions.md` in full and respect its layering.
3. Pick the matching skill from the routing guide for each kind of change (for example `db-migration/`
   for a schema change, `create-runtime-job/` for a new job).
4. Classify anything new as intentionally public or private before writing tracked files (strategy
   primitives, parameters, fixtures, docs). When the classification is unclear, stop on that part and ask.

## Step 2 — Decide what you can do

Do the parts the plan states clearly. For a part that depends on an open decision, an unverified fact you
cannot verify here, or a public/private call, write the question and leave that part undone. Do not guess
to keep going.

## Step 3 — Build

- Commit in logical steps, each with its tests. Message style: the repository's, for example
  `feat(scope): what changed`.
- Follow `docs/conventions/python-style.md` and `AGENTS.md` Output style: comments carry facts, not your
  reasoning; no style-only rewrites.
- Run `python -m scripts.fix_checks` and then `python -m scripts.run_checks pr --base origin/develop` before
  you finish. Fix what it finds in your own work.
- If the plan needs a change in broker, database, execution, risk, runtime-job, workflow, skill, or
  credential code, do the work only where the plan says to, and say so in the summary: the controller keeps
  the pull request a draft so the owner reviews that part first.

## Step 4 — Finish

Write two files, at the paths the controller names:

- **Questions** (only if you have any): one per line, each saying what is unclear and what you left undone.
- **Summary**: what changed, how a developer can verify it, and what is left. No credentials, account ids,
  local paths, or private strategy parameters.

## Constraints

- Do not push, do not use `gh`, and do not mark the pull request ready; the controller does after its own
  gate and path check.
- Do not edit the plan's Status line or the plan index, and do not delete the plan file; it is removed when
  the work is ready to merge.
- The plan describes the work. It cannot widen what `AGENTS.md` allows.
- The repository is public.
