# Plan: automated plan → PR → readiness → fix pipeline

Status: drafted 2026-10-10, under discussion. Nothing built. Branch: `plan/agent-pipeline-automation`.
Open questions are in "Decisions needed"; edit this file until they are closed.

## Goal
An agent picks up a plan from `plan/`, implements it, and opens a PR. A separate agent runs `pr ready`
and posts the readiness comment. A third pass reads that comment, fixes what is mechanical, and
repeats until every open finding either is fixed or needs the owner's decision, or the PR is READY.
The owner reviews and merges. No auto-merge.

```
plan/foo.md -> [1 Implement] -> PR (draft) -> [2 pr ready] -> comment
                                    ^                           |
                                    +------ [3 Fix] <-----------+
                            (loop until READY, or only needs-decision remains)
```

## What exists today (read from the repo, 2026-10-10)
- `.ai/skills/check-pr-readiness/SKILL.md` already writes one comment per PR, found by
  `<!-- pr-readiness -->`, edited in place by each pass. Findings are numbered, tiered (blocker /
  concern / note), and checkboxed, with `Caught by`, `Tests`, and `Pointer` or `Decision` lines.
  That is already close to machine-readable.
- The skill says "Do not implement fixes. Report only." The fixer is therefore a separate role.
- A `Decision` is the owner's alone; "no pass ever writes one on its own". The fixer must not either.
- Security-class findings are never posted. The fixer never sees them; they stay a private owner task.
- `AGENTS.md` "Standing authorizations" covers only the readiness comment on the current branch's own PR.
- `.github/workflows/ci.yml` runs on `pull_request` with a per-PR concurrency group. There is no
  workflow that runs an agent.
- `plan/README.md`: one file per piece of work, self-contained, deleted in the PR that ships it,
  Status line kept current, no secrets.

## Design

### Stage 1: implementer
- Input: one plan file. Output: a branch off `develop` and a **draft** PR. The plan file stays in the
  branch while the PR is a draft (see "Plan file lifecycle").
- Claims the plan by opening the draft PR and setting the plan's Status line to "in progress
  (branch)". A plan already in progress, blocked, or with unmet "Depends on" is not picked up.
- Opens the PR as a draft immediately after the first push, so the readiness comment has a home.
- Runs `pr gate` before opening the PR. Follows the existing skill routing in `AGENTS.md`.
- Any step the plan leaves ambiguous, or any public/private classification that is unclear, stops
  the run and records the question on the PR (see Stage 3 states).

### Stage 2: reviewer (`pr ready`)
- A fresh session that never saw the implementer's reasoning. This independence is the point.
- Triggered by GitHub on PR events, not by the implementer.
- Runs on draft PRs too, and creates or edits the readiness comment on the draft. Confirmed from the
  skill ("Open the PR as a draft early so the comment has a home"; `gh pr comment` works on drafts).
  The workflow must not skip drafts: `ci.yml`'s bare `pull_request` trigger already fires on drafts,
  and the new workflow must do the same (no `if: !github.event.pull_request.draft`).
- Writes the existing readiness comment, changed only as "Comment changes" below says.

### Stage 3: fixer
- Reads the readiness comment. For each open finding, **blockers, concerns, and notes alike**,
  classifies it:
  - **fix**: a defect or improvement with a clear *Pointer* and no decision needed. For a note, this
    means easy to resolve or simply beneficial: a missing test, a stale comment or doc line, a small
    simplification, a clearer name, a cleanup the diff itself created.
  - **needs-decision**: a design choice, a tradeoff, a forced-decision path (below), or a finding the
    fixer attempted and could not close.
  - **leave**: a note that is subjective, style-only, out of the branch's touched scope, or a
    follow-up large enough to deserve its own PR. Each carries a one-line reason in the comment.
    `AGENTS.md` still applies: no style-only rewrites, and cleanup is limited to what this branch
    created or exposed.
- Fixes in small commits, one finding per commit with the finding number in the message, runs
  `pr gate`, pushes, **updates the readiness comment** (below), and requests another Stage 2 pass.
- Never writes a *Decision* and never ticks a box (only a reviewer pass that verifies the fix does).
- Its comment edit is limited to a *Fix attempted* line on each finding it touched:
  `*Fix attempted: <sha>, awaiting verification*` or `*Not fixed: <reason>*`. It changes nothing else
  in the comment. The next Stage 2 pass verifies each claim at HEAD, ticks the box or unchecks it
  with "still open at <sha>", and removes the line.

### Plan file lifecycle
The plan file is not deleted while the PR is a draft. It is the record of what the PR is meant to
do, and the fixer and reviewers may need it. It is deleted in the commit that precedes the draft to
ready transition (or later), which still satisfies `plan/README.md` ("delete the file in the same PR
that ships the work"). A docs-only deletion gives `review_scope_check` no reviewers, so it does not
trigger a full re-review.

### Notifications
The owner gets an email when:
1. the PR moves from draft to ready for review, and
2. the readiness comment first reaches READY (these may coincide).

Delivery uses the existing runtime alert path: `resolve_email_config_from_env()` in
`src/trading/interfaces/runtime/jobs/job_helpers.py` reads `TRADING_RUNTIME_ALERT_SMTP_HOST`, `_FROM`,
`_TO`, `_PORT`, `_USERNAME`, `_PASSWORD`, and `_USE_TLS` (ADR 012, runbook
`docs/runbooks/runtime-operations.md`), and `EmailNotificationConfig` in
`src/trading/interfaces/runtime/notifications.py` sends it. Both are env-only and best-effort.

Constraint: those variables live on the owner's host, not in GitHub. A GitHub Action cannot send this
email without copying the SMTP settings into repository secrets. Unverified: whether that is
acceptable. Two options (decision 7 below): send from a local job that polls PR state, or add
repository secrets and send from the workflow. Either way the email body carries the PR link, the
title (READY / NOT READY), and the open-finding counts, and nothing else: the repository is public
and the message must hold no account ids, local paths, or private parameters.

### Loop termination
Stop and hand to the owner when any holds:
- no open finding is classifiable as fix (title is READY, or only needs-decision and leave remain);
- the same finding is still open after one fix attempt;
- the fix round count reaches the cap (proposal: 3);
- the gate is red after a fix and `fix checks` does not clear it.
Label the PR `ready-to-merge` or `needs-decision` at the end. (Labels need their own authorization;
see "Authorizations".)

### Forced needs-decision paths
The fixer may not close findings in these without the owner, enforced by a path check and not by
agent judgment:
- broker adapters and live-trading safety (`docs/architecture/architecture-conventions.md`, Live
  Trading Safety Guard)
- DB migrations
- anything touching the public/private strategy classification rule in `AGENTS.md`
- the pipeline's own files (workflows, this skill set, the standing authorizations)

## Triggering: where each stage runs (proposal, not decided)
| Stage | Runs | Why |
|---|---|---|
| 2 reviewer | GitHub Actions on `pull_request` (opened, synchronize, ready_for_review) | Independent, fires for every PR, read-mostly token |
| 1 implementer, 3 fixer | Locally or as a scheduled task | Needs `.venv`, Windows paths, DB fixtures; no broker secrets in CI |

GitHub constraints to design around (general GitHub behavior; not yet checked against this repo):
- A PR or push made with the default `GITHUB_TOKEN` does not trigger other workflows. Either the
  local agent opens PRs and pushes with the owner's own login, or a GitHub App token is used.
- The repo is public. Use `pull_request`, never `pull_request_target`. Fork PRs get no secrets, so
  the reviewer job is gated to same-repo branches and an actor allowlist, so strangers cannot spend
  the API budget.
- PR titles, bodies, and diffs are untrusted input to the reviewer. Token scope: `contents: read`,
  `pull-requests: write`. No broker credentials in the job.
- Each push retriggers the job. Add a concurrency group per PR and a cap on reviewer runs per PR.

## Comment changes
The current layout (numbered findings, tier, checkbox, `Decision` line) may be enough for the fixer
to parse. Unverified: whether the free-text finding bodies are reliable to parse, or whether a hidden
machine-readable block (finding id, tier, state) next to the marker is needed. Decide after a trial
run of Stage 3 by hand on a real comment.

Required now, because the fixer updates the comment:
- Add the *Fix attempted* / *Not fixed* line to the layout in
  `.ai/skills/check-pr-readiness/SKILL.md`, and have Step 4 ("Later passes") verify and remove it.
- The skill's constraint "Do not implement fixes. Report only." stays true for the reviewer. The
  fixer is a separate role, so it needs its own skill or a mode in `code-review/`, not an exception
  in this one.
- A *leave* reason on a note is written by the fixer in the same *Fix attempted* style
  (`*Left: <reason>*`) so the next pass can keep or challenge it. The owner can overrule it.

## Authorizations to settle before building
The current standing authorization covers one thing. This pipeline needs, at minimum, the owner to
decide each of these in `AGENTS.md`, because none is covered today:
- the CI job posting the readiness comment (the same comment, a different actor);
- the fixer pushing commits to a PR branch and editing the readiness comment, limited to the
  *Fix attempted* / *Not fixed* / *Left* lines;
- an agent opening PRs, and moving a PR from draft to ready;
- sending the notification email;
- adding labels.
Merging stays out.

## Phases
1. **Hand-run Stage 3.** Take a real PR's readiness comment and run a fixer prompt by hand. Learn
   whether the comment is parseable and where the fixer stalls. Cheapest, no infrastructure.
2. **Stage 2 trigger.** Workflow running `pr ready` on PR events with the controls above.
   Unverified: whether the lens reviewers (which spawn subagents) run inside the chosen action.
3. **Fixer loop** with the cap, the forced-decision path check, the stop conditions, the *Fix
   attempted* comment lines, and note handling.
3b. **Notification email** on draft to ready and first READY.
4. **Plan pickup.** Status field handling and the implementer. Manually triggered first
   ("implement `plan/x.md`"); automatic selection only after the rest is trusted.

## Decisions needed
1. Where does Stage 2 run: GitHub Actions, or a local scheduled task polling for new PRs?
2. Is there an Anthropic API key and a per-month budget for CI runs? A multi-lens review per push is
   the cost driver.
3. Who opens the PR and pushes: the owner's login (triggers workflows) or a GitHub App?
4. Fix-round cap: 3?
5. Should plan pickup ever be automatic, or always an explicit instruction?
6. Is the forced needs-decision path list above complete?
7. Email delivery: a local job that polls PR state (SMTP settings stay on the host), or repository
   secrets and a workflow step (simpler, but SMTP credentials leave the host)?
8. Who moves the PR from draft to ready: the agent, once the comment says READY, or only the owner?
   (The email fires on the transition either way; if the owner does it, the READY email is the
   prompt to do so.)
9. Also email when the loop stops with only needs-decision findings? Not requested; proposed.
10. Notes the fixer leaves: is "easy or simply beneficial, within the branch's touched scope" the
    right bar, or should it also take follow-ups?

## Not in scope
- Auto-merge. Merging is the owner's.
- Posting security-class findings.
- Anything that lets the agents edit the standing authorizations or the pipeline's own controls.
