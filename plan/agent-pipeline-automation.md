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
- Input: one plan file. Output: a branch off `develop`, a draft PR, plan file deleted in that PR.
- Claims the plan by opening the draft PR and setting the plan's Status line to "in progress
  (branch)". A plan already in progress, blocked, or with unmet "Depends on" is not picked up.
- Runs `pr gate` before opening the PR. Follows the existing skill routing in `AGENTS.md`.
- Any step the plan leaves ambiguous, or any public/private classification that is unclear, stops
  the run and records the question on the PR (see Stage 3 states).

### Stage 2: reviewer (`pr ready`)
- A fresh session that never saw the implementer's reasoning. This independence is the point.
- Triggered by GitHub on PR events, not by the implementer.
- Writes the existing readiness comment, unchanged in format unless "Comment changes" below says so.

### Stage 3: fixer
- Reads the readiness comment. For each open finding, classifies it:
  - **fix**: a defect with a clear *Pointer* and a *Tests* line it can satisfy.
  - **needs-decision**: a design choice, a tradeoff, a forced-decision path (below), or a finding the
    fixer attempted and could not close.
- Fixes in small commits, runs `pr gate`, pushes, and requests another Stage 2 pass.
- Never writes a *Decision*, never ticks a box (only a reviewer pass that verifies the fix does),
  never edits the comment.

### Loop termination
Stop and hand to the owner when any holds:
- no open finding is classifiable as fix (title is READY, or only needs-decision remains);
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
Possibly none. The current layout (numbered findings, tier, checkbox, `Decision` line) may be enough
for the fixer to parse. Unverified: whether the free-text finding bodies are reliable to parse, or
whether a hidden machine-readable block (finding id, tier, state) next to the marker is needed.
Decide after a trial run of Stage 3 by hand on a real comment.

## Authorizations to settle before building
The current standing authorization covers one thing. This pipeline needs, at minimum, the owner to
decide each of these in `AGENTS.md`, because none is covered today:
- the CI job posting the readiness comment (the same comment, a different actor);
- the fixer pushing commits to a PR branch;
- adding labels;
- an agent opening PRs.
Merging stays out.

## Phases
1. **Hand-run Stage 3.** Take a real PR's readiness comment and run a fixer prompt by hand. Learn
   whether the comment is parseable and where the fixer stalls. Cheapest, no infrastructure.
2. **Stage 2 trigger.** Workflow running `pr ready` on PR events with the controls above.
   Unverified: whether the lens reviewers (which spawn subagents) run inside the chosen action.
3. **Fixer loop** with the cap, the forced-decision path check, and the stop conditions.
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

## Not in scope
- Auto-merge. Merging is the owner's.
- Posting security-class findings.
- Anything that lets the agents edit the standing authorizations or the pipeline's own controls.
