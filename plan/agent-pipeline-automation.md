# Plan: automated plan → PR → readiness → fix pipeline

Status: in progress. Branch: `plan/agent-pipeline-automation` (PR #301). All twelve decisions are settled
(see "Decisions"). Built and validated on this branch: the forge CLI (`scripts/forge/`), the Stage 2
reviewer workflow (`.github/workflows/pr-readiness.yml`), and the Stage 3 fixer skill, hand-run through two
rounds to READY. The unattended loop (`fix-loop`) was live-tested for one round, and plan pickup (Stage 1,
`implement-plan`) was live-tested end to end on a throwaway plan. Not yet run live: the notification email.

## Goal
An agent picks up a plan from `plan/`, implements it, and opens a PR. A separate agent runs `pr ready`
and posts the readiness comment. A third pass reads that comment, fixes what is mechanical, and
repeats until every open finding either is fixed or needs the owner's decision, or the PR is READY.
The owner reviews and merges. No auto-merge.

```
plan/foo.md -> [1 Implement] -> draft PR -> gate green -> PR ready for review
                                                              |
                                                       [2 pr ready] -> comment
                                                              ^           |
                                                              +-- [3 Fix] <+
              (loop until READY, or only needs-decision remains; email owner either way)
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
- Input: one plan file. Output: a branch off `develop` and a PR that it moves out of draft itself.
  The plan file stays in the branch until the loop ends (see "Plan file lifecycle").
- Claims the plan by opening a **draft** PR after the first push and setting the plan's Status line
  to "in progress (branch)". The draft is only the visible claim; no review runs on it. A plan
  already in progress, blocked, or with unmet "Depends on" is not picked up.
- When the implementation is complete and `pr gate` is green, it marks the PR ready for review. That
  transition is what starts Stage 2. It uses the owner's login, because a transition made with the
  default workflow token would not trigger the workflow.
- Follows the existing skill routing in `AGENTS.md`.
- Any step the plan leaves ambiguous, or any public/private classification that is unclear, stops
  the run and records the question on the PR (see Stage 3 states).

### Stage 2: reviewer (`pr ready`)
- A fresh session that never saw the implementer's reasoning. This independence is the point.
- Triggered by GitHub on PR events (`opened`, `ready_for_review`, `synchronize`), not by the
  implementer. It reviews **non-draft PRs only** (decision 12): the workflow skips drafts with its
  own condition. The first readiness comment is therefore created on the first pass after the PR
  leaves draft.
- Runs the reviewer as a direct non-interactive CLI call (`claude -p`), not through the official
  action (decision 1). The docs reportedly say the action skips draft PRs; with our own condition
  that no longer matters for the design, and the direct call keeps the trigger layer thin.
- Writes the existing readiness comment, changed only as "Comment changes" below says.
- `.ai/skills/check-pr-readiness/SKILL.md` currently says "Open the PR as a draft early so the
  comment has a home". That line changes to match: the comment's home is the PR once it is ready.

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
The plan file is not deleted while the PR is a draft, and it stays after the PR leaves draft. It is
the record of what the PR is meant to do, and the fixer and reviewers read it. It is deleted in the
final commit of the loop, once the comment says READY. That satisfies `plan/README.md` ("delete the
file in the same PR that ships the work"). The deletion makes the READY comment one commit stale; the
next pass sees a docs-only increment, `review_scope_check` suggests no reviewers, and the pass
re-confirms READY by hand at low cost. The owner is emailed after that confirming pass, not before.
If the loop instead stops on needs-decision, the plan file stays.

### Notifications
The owner gets an email when:
1. the readiness comment reaches READY and the plan-file deletion pass has confirmed it, and
2. the loop stops with only needs-decision (or left) findings, or on a cap or red gate (decision 9).

The draft to ready transition is not a notification: the implementer makes it itself right after
the local gate is green, so an email there would be noise. Add one if wanted.

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
- the fix round count reaches the cap (3, decision 4);
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
- credential handling: `.env*` files and any code that reads secrets
- the runtime schedule and job inventory (they change what runs unattended)
- `docs/adr/` (accepted decisions are the owner's to change)

## Tool independence
The pipeline's logic must not depend on GitHub. Three layers, only the bottom one platform-specific:

1. **Policy and behavior** (platform-neutral): the skills in `.ai/skills/`, the readiness comment
   format and its `<!-- pr-readiness -->` marker, the fixer rules, the stop conditions, the forced
   needs-decision paths. These say "pull request", "draft", "readiness comment", never `gh`.
2. **A forge interface** (platform-neutral surface, one adapter per platform): the only code that
   knows how to talk to the host. Proposed as a small CLI in `scripts/`, e.g.
   `python -m scripts.forge <operation>`, with a GitHub adapter first and room for GitLab or others.
   Operations the pipeline needs:
   - `pr-info`: number, base, head ref and sha, draft flag, state, URL
   - `list-prs`: open PRs, optionally only drafts or only ones lacking a readiness comment
   - `comment-get` / `comment-upsert`: the marker-tagged comment, found by marker
   - `ci-status <sha>`: pass, fail, or pending per check, for that commit
   - `set-ready` / `set-draft`, `add-label`
   - `open-pr`
   The skills call these instead of `gh`. Today `check-pr-readiness/SKILL.md` calls `gh pr view`,
   `gh run list`, `gh pr checks`, and `gh api .../issues/<n>/comments` directly; those move behind
   the interface.
3. **Triggers and runners** (platform-specific, thin): a workflow file that fires on PR events and
   runs one command (a single review entry point). Everything else is
   behind that command. Moving to another forge means rewriting this file and writing one adapter.

The notification email (above) is already platform-neutral because it uses the runtime SMTP settings.
The agent runner is the same idea: the prompt is "run `pr ready`", whether that is started by an
Actions step, a GitLab job, or a local scheduler.

### MCP server or CLI for the forge interface?
An MCP server would work, but the benefit that matters is not MCP-specific:
- **Narrow, auditable permissions.** An agent with `gh` or a shell can do anything the token allows.
  A fixed set of operations (`comment-upsert` only on the marker comment, no merge, no other
  comments) turns the standing authorization into something the tool enforces. A CLI with an allowed-tools
  rule such as `Bash(python -m scripts.forge:*)` gives the same narrowing.
- **Platform independence.** Same either way.
- **MCP's extra value** is use from clients that cannot shell out, or sharing one server across
  tools. This repo's agents run commands, so it adds a server to build, run, authenticate, and keep
  alive for little gain.
- Recommendation: build the CLI with unit tests under `tests/`, matching the repo's `scripts/`
  conventions. Revisit an MCP wrapper only if a client needs it. Unverified: how well the
  allowed-tools restriction holds when the agent can still reach the shell directly; the CLI narrows
  the instructions, but a separately scoped token is the real enforcement.

## Verified vs unverified
A docs check on 2026-10-10 (by a research subagent, summarized; its report footer carried a wrong
fetch date, so recheck details against the live docs before building):

| Claim | Status |
|---|---|
| `anthropics/claude-code-action` supports `pull_request` (opened, synchronize, ready_for_review, reopened), `issue_comment`, `schedule` | reported, not tested (the direct CLI call was used) |
| The action skips draft and closed PRs | reported, not tested; our own workflow condition skips drafts (confirmed) |
| Same-repo PRs work; fork PRs get no secrets | reported |
| Subscription auth: `claude setup-token` (one-year OAuth token) | **confirmed** with `CLAUDE_CODE_OAUTH_TOKEN` and the CLI |
| Subscription token does not work with `--bare` | reported |
| Normal (non-bare) mode loads `CLAUDE.md`, `.ai/skills/`, and subagents, so lens reviewers can run | **confirmed** |
| Subscription usage limits and how CI runs share them with interactive use | about 1% of the daily limit for the first pass; sharing with interactive use still unverified |
| GitLab integration is beta, authenticates by API key, Bedrock, or Vertex (no subscription token listed), and mention triggers need a webhook listener | reported |
| Claude Code on the web scheduled routines need a claude.ai login and suit scheduled work, not PR events | reported |

Everything marked reported or unconfirmed is verified by a small spike before Phase 2 is built:
a throwaway workflow on a test PR that runs the reviewer step as a direct CLI call with the
subscription token, and records what posts, which skills and subagents load, how it behaves on
`ready_for_review` vs `synchronize`, and what it costs against the plan's limits. The official
action's draft behavior is no longer on the critical path (decisions 1 and 12); test it only if we
later want the action.

## Phase 0: verification spike (scope)
Purpose: retire the unverified claims above with the least work. If items 1-5 fail, nothing later
matters; if they pass, the biggest risks are gone.

| # | Question | How it is answered |
|---|---|---|
| 1 | Does the subscription token authenticate `claude -p` on a GitHub runner? | A trivial prompt returns text. |
| 2 | Do `AGENTS.md`/`CLAUDE.md` and the `.ai/skills/` skills load in that mode? | Ask it to name the `pr ready` shortcut and the six steps of `check-pr-readiness`. |
| 3 | Can the lens reviewers spawn subagents? | A prompt that spawns one subagent and reports its result. |
| 4 | Can it do `pr ready` end to end on the runner? | Run `pr ready` on a small diff; steps 1-6 complete. The runner uses the Python setup `ci.yml` already uses. |
| 5 | Can it create, then edit, the marker comment with only `pull-requests: write`? | Run twice on one PR: one comment created, then that same comment edited. |
| 6 | Does the trigger and draft skip work? | No run while the PR is a draft; a run on `ready_for_review`; a re-run on `synchronize`. |
| 7 | What does a review cost? | `--output-format json` usage and duration, plus the owner's plan-usage reading before and after. |
| 8 | Which permission flags does non-interactive mode need? | Record the `--allowedTools` and permission settings required to run unattended. |

Shape:
- A throwaway branch `spike/agent-review-ci` with a throwaway workflow and a small harmless code
  change (so `review_scope_check` selects at least one lens and exercises item 3). The PR starts as a
  draft, then is marked ready.
- The workflow runs only for same-repo PRs from that branch name. Fork PRs cannot read the secret
  anyway; the branch condition is a second guard because the repo is public.
- Out of scope: the forge CLI, the fixer, the email, plan pickup.

Owner actions (agents do not handle credentials): run `claude setup-token` and add the result as a
repository secret; read the plan-usage meter before and after each run.

Cleanup: close the PR; delete the branch, the workflow, and the secret (or rotate the token). Record
results in a "Spike results" section here and update the "Verified vs unverified" table.

Settled by the owner, 2026-10-10:
- The spike PR is public, in this repo. Its comment holds review text only: no keys, paths, or
  account ids.
- Only the direct `claude -p` call is tested; the official action is skipped (decision 1).
- Run on the default model first; try a cheaper one only if cost is a problem.

## Phase 0 results (2026-10-10, spike PR #299, now closed)
A throwaway workflow ran `claude -p` (Claude Code 2.1.296, subscription token, default model) on a
GitHub runner through three passes on one PR. The owner measured about 1% of the daily plan limit
after the first pass.

| # | Question | Result |
|---|---|---|
| 1 | Subscription token authenticates `claude -p` on a runner | **Pass** |
| 2 | `AGENTS.md`, `CLAUDE.md`, and `.ai/skills/` load | **Pass**, shown by the skill's exact comment layout and six-step table. The probe's answer text went only to the job summary, which the API cannot read. |
| 3 | Subagents work | **Pass**. Three lens reviewers ran separately on pass 1, each labelled Sonnet. |
| 4 | `pr ready` end to end | **Pass**. Gate ran on `origin/develop`, 139 tests passed, CI checked at HEAD; about 2.6 minutes for the first pass. |
| 5 | Create then edit the marker comment with `pull-requests: write` only | **Pass**. One comment, edited in place across three passes. |
| 6 | Draft skip and triggers | **Pass**. Skipped on the draft; ran on `ready_for_review`; re-ran on `synchronize`. |
| 7 | Cost | Reported API-equivalent cost: probe about $0.09; `pr ready` about $0.50 (pass 1), $0.27 (pass 2), $0.14 (pass 3). The first pass's JSON reported 2 turns and 5 s against 155 s of wall time, so the JSON metrics are not reliable. The plan-usage meter is the real figure. |
| 8 | Permission flags | **Pass**. `Read,Glob,Grep,Skill,Agent,Write` plus `Bash` limited to git, gh, python, `.venv/bin/python`, jq, cat, ls produced no `permission_denials`. |

### Continuity finding (resolved by a workaround, not yet by design)
Pass 2 ran without the previous comment in its prompt. It reset the pass number to 1, renumbered the
findings, dropped the notes that had been fixed instead of carrying them as checked lines, and
dropped one open note with no reason. Pass 3 was given the previous comment in its prompt with an
explicit later-pass instruction. It incremented the pass number, kept finding numbers, checked the
fixed note with its fix sha, kept the open ones, and kept the pass history. So an agent cannot be
trusted to reconstruct state; the runner must supply it.

## Issues found in the spike (to address before or while building)
1. **Comment continuity.** Inject the previous comment into every later-pass prompt (proven by
   pass 3), or move state into a hidden machine-readable block read and written by the forge CLI.
   A lost *Decision* line is silent data loss, so verify that a Decision survives a pass by test
   before trusting this.
2. **Reviewers ran as one combined run in pass 2** ("the three reviewers ran as one combined agent
   run, not three separate runs"). Pass 1 ran them separately. The cause is unknown: possibly the
   agent's own choice, possibly a skill ambiguity. Needs more detail: record the stream-json
   transcript for a run (`--output-format stream-json`, saved as an artifact) so the Agent calls can
   be seen, then decide whether the skill must say "one agent per lens".
3. **`continue-on-error` hides failures.** A failed agent step still shows a green job. The real
   workflow must read `is_error` and fail, and must fail loudly on an empty or unparsable JSON.
4. **Review races CI.** The reviewer and CI start on the same push, so Step 2 reports "pending" and
   the title stays NOT READY for that reason alone. The real pipeline should wait for CI to finish
   (for example a `workflow_run` trigger) or re-run on CI completion.
5. **Cost metrics.** The JSON `duration_ms`, `num_turns`, and cost undercounted on pass 1. Do not
   budget from them; use the plan-usage meter.
6. **Probe output is invisible to the API.** Anything the agent says that only reaches
   `$GITHUB_STEP_SUMMARY` cannot be read by a script. The real pipeline logs or uploads what it
   needs.
7. **Unpinned Claude Code.** The runner installed whatever was latest (2.1.296 that day). Pin the
   version, and upgrade deliberately.
8. **`.venv` on the runner.** `AGENTS.md` says to stop and ask if `./.venv` is missing. The workflow
   creates it first, which worked. Keep that step.
9. **Frontend dependencies.** The spike did not install them; a diff touching the frontend would
   fail the frontend gate on the runner (raised by the reviewer). The real workflow installs them
   when the diff needs it.
10. **Base ref.** The checkout has `origin/develop` but no local `develop`, so the prompt had to name
    `origin/develop`. Move that into the skill or the forge CLI so no prompt carries it.
11. **Closed findings sit after the open ones** without their tier heading. Acceptable per the
    skill's layout, but confirm it matches what the fixer parses.
12. **Throwaway files in a mergeable PR.** The reviewer correctly flagged the spike workflow as a
    merge hazard. Not a pipeline issue; noted because the same check protects real PRs.

### Status after building Stage 2 (2026-10-10, validated on PR #301)
| Issue | Status |
|---|---|
| 1 Continuity | Fixed: `review-context` supplies the previous comment; `check-body` requires the pass number to be the previous plus one. Verified across passes. |
| 2 Reviewers ran as one run | Cause was the prompt wording ("running unattended"). The explicit Step 4 instruction fixed it: four separate Sonnet subagents ran, confirmed in the saved transcript. |
| 3 Failures hidden | Fixed: the job fails on an agent error, a missing result, a bad body, a moved head, or the pass cap. |
| 4 Review races CI | Fixed in code: `wait_for_ci` waits until the same checks are seen twice, treats `none` as starting for a grace period, and excludes the reviewer's own check. A reviewer found the first version returned too early; the fix has unit tests but has not been observed on a slow CI run. |
| 5 Cost metrics | The agent step reports cost, turns, and duration in the job summary; treat the first pass's numbers with care. |
| 6 Output invisible to the API | Fixed: the transcript artifact is available behind `READINESS_SAVE_TRANSCRIPT`. |
| 7 Unpinned version | Fixed: pinned in the workflow. |
| 8 `.venv`, 9 frontend dependencies, 10 base ref | Fixed. |
| 11 Closed-finding placement | Unchanged; the layout held across passes. |
| 13 (new) A gate-stopped first pass let a later pass skip the reviewers and say READY | Fixed in the skill: READY requires the suggested reviewers to have run on the whole diff, and the incremental shortcut applies only after such a pass. |

Found by the Stage 2 reviewers on this branch, and fixed with it: the CI wait returning on `none`, a pass
cap that could fail open, an unused expected-head check, test stubs that ignored `--exclude` and
`--author`, malformed `gh` output producing a traceback, and the prompt passed as one argument (now on
stdin, which works.

Validation outcome (PR #301, three passes on the Stage 2 workflow): the job runs the gate and the four
lens reviewers as separate subagents, merges their findings into one comment, edits it in place, and
carries findings forward across passes (pass 3 closed 15 and reached READY). Its guards refused one
comment (a false positive on quoted path prefixes, since fixed) and posted nothing. About 1 USD of
API-equivalent cost for a pass with reviewers, far less for a pass that re-verifies by hand. Still
unobserved: a slow CI run against the new wait (unit-tested only).

## Stage 3 build and hand-run results (2026-10-10, PR #301)
Hand-run: two fixer rounds on this PR's own readiness comment reached READY (pass 7). Round 1 fixed one
concern and four notes; round 2 fixed a new concern and two notes; the reviewer verified each fix with
its sha, removed the `Fix attempted` lines, and carried `Not fixed` and `Left` lines forward. The fixer
refused to edit a skill file (a guarded path) and recorded it. Each round's own fixes raised smaller
findings, which is the shape the three-round cap expects.

Skill gaps found and fixed with the owner's approval: partial fixes get two lines; an earlier attempt is
found from the commit log, because the reviewer removes the line; a status line is plain ASCII text with
no colon, slash, backtick, link, or bracket; an edit may only add lines.

Built from it: `check-body --edit-of` (additions-only, plain-text status lines); `findings.py` (verdict and
which open findings a fixer can still work); `guarded_paths.py` (broker, database, execution, risk, and
runtime code from the review-scope rules, plus the forge tool, workflows, skills, `AGENTS.md`, ADRs,
`.env*`, and `local/`); `fix_loop.py` (one round: agent, path check, body check, post, push, wait for the
next pass; stops at READY, nothing left for a fixer, three rounds, or anything unexplained); `local.py`
(real git, headless `claude`, email through the runtime alert settings); and the `fix-loop` command.
The agent commits locally and writes a body to a file; the loop checks paths and body before it posts or
pushes, the same split Stage 2 uses.

Live test (two runs on a throwaway pull request, run from the owner's terminal): the first, on the
owner's default model, fixed a missing-test finding in 60 s and about 0.41 USD, and left or declined the
rest. It showed rough edges, now fixed: a failed agent buried its reason in a JSON dump, the repo's
own pytest executable was denied, and a missing SMTP configuration was silent. The second, on Sonnet
(now the default, `--model` overrides), fixed a code-and-tests finding, recorded `Not fixed` for a design
question and for a skills-folder wording nit (a guarded path), and `Left` for a rename, in 12 turns and
44 s. Both ended with the expected "next review pass did not arrive", since the reviewer does not run on
a pull request into a non-develop base. Headless `claude` is not signed in by the desktop app: the owner
signs in once in the terminal with `/login`.

Still unverified: a loop that crosses a real review pass (round, push, reviewer, next round), email
delivery, and a start without the owner's terminal. The unattended run also needs a standing
authorization in `AGENTS.md` for pushing to a pull request branch and editing the comment; the owner
grants it. Decision 22 (status-line placement) was accepted by the owner; finding 21 (`comment-upsert`
enforcing the edit rule itself) is still the owner's.

## Stage 1 build and live test (2026-10-10)
Built: `implement-plan --plan plan/<file>` (controller `implement.py`, plan reading and claiming in
`plans.py`, skill `implement-plan`). It refuses a plan that is unlisted, in progress, blocked, or has
unconfirmed dependencies; creates the branch off the base; commits the claim; opens a draft pull request;
runs a headless Sonnet agent that cannot push; then pushes, runs the gate itself, checks guarded paths, and
takes the pull request out of draft only when the agent committed, raised no question, the gate passed, and
nothing guarded was touched.

Live test, from the owner's terminal, on a throwaway plan (a small pure helper with tests and a map row),
with the plan branch as the base because `develop` lacks the pipeline: the agent used 14 turns and about
71 s, the gate passed, no guarded path was touched, and the pull request left draft with an edge case
handled that the plan only implied (`fullmatch`, so a trailing newline is rejected). Two commands were
denied (a `git checkout` of generated files), which led to the one real defect: `fix_checks` regenerates
`api.json` and `software.json` with CRLF line endings on Windows, which left the working tree dirty and
would have blocked the next run's clean-tree check. The generators now write LF, with a test.

Question run (2026-10-11), on a real plan: `more-trading-evidence.md`, which is mostly open decisions and
unverified claims. The agent built nothing ("building any part would mean guessing"), asked real questions
(which tickers, cap evidence it could not get without run logs, design A or B), and noted that
`configure_book` may already cover the universe change. The pull request stayed a draft with only the claim
commit, and its description carried the summary and the questions. 9 turns, about 21 s. Roughness: one
question was a restatement, and the summary pointed at a file that no longer exists once the run ends.

Plan-file removal (built 2026-10-11): when `fix-loop` sees READY and the branch claimed a plan (its Status
says "in progress (branch `<this branch>`)"), it removes that plan file and its index row in one commit,
pushes, and waits for the docs-only pass that confirms READY; a NOT READY result sends it back to fixing.
A plan this branch did not claim is never removed, so the pipeline plan itself is the owner's to remove.
Tested with fakes and real git; not yet run live.

Chained start (built 2026-10-11, at the owner's request): `implement-plan` does not need a separate fixer
start. When the pull request leaves draft it waits for the review's first comment, then runs the fixer
loop, and sends one email at the end. Plan pickup itself stays manual: the owner runs it when a plan is
ready. `--no-fix` opts out. Both loops now trust `github-actions[bot]` and the owner by default; before this,
the default trusted only the owner, which would have ignored the review workflow's comment.

Still open for Stage 1: a run on a plan that needs a guarded path or ends with a red gate (covered by tests,
not run live), and a start that does not need the owner's terminal.

## Triggering: where each stage runs (decided: decisions 1, 3, 12)
| Stage | Runs | Why |
|---|---|---|
| 2 reviewer | GitHub Actions on `pull_request` (opened, ready_for_review, synchronize), non-draft only, direct `claude -p` | Independent, fires for every ready PR, read-mostly token |
| 1 implementer, 3 fixer | Locally or as a scheduled task | Needs `.venv`, Windows paths, DB fixtures; no broker secrets in CI |

### Authentication for the agent runs
| Option | Billing and limits | Where it works |
|---|---|---|
| `ANTHROPIC_API_KEY` repository secret | Per token, separate from the subscription. Predictable cost, no effect on interactive use. | Actions, headless, `--bare` |
| Subscription OAuth token (`claude setup-token`, one year) | Draws on the plan's usage limits. Unverified: whether CI runs share the window with interactive sessions (assumed yes). A busy review loop could crowd out interactive work. | Actions, headless `claude -p`; not `--bare` |
| Bedrock, Vertex, Foundry | Cloud billing, OIDC with no static key | Actions, headless |

Decision 2: start with the subscription token (no per-token bill), switch to an API key if CI runs
crowd out interactive sessions. Both are first-class options, so a subscription is not a blocker. A
token is a long-lived credential in a public repo's secrets: scope it to the reviewer job, rotate at
expiry, and keep it out of fork-triggered runs. Unverified: whether the plan's terms allow
automated CI use at this volume; check the current terms before relying on it.

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
0. **Verification spike**: done 2026-10-10 (see "Phase 0 results"). Its "Issues found in the spike" list feeds the phases below.
0b. **Forge interface.** The `scripts/forge` CLI and GitHub adapter, with tests; point the readiness
   skill at it instead of raw `gh`.
1. **Hand-run Stage 3.** Take a real PR's readiness comment and run a fixer prompt by hand. Learn
   whether the comment is parseable and where the fixer stalls. Cheapest, no infrastructure.
2. **Stage 2 trigger.** Workflow running `pr ready` on PR events with the controls above.
   Unverified: whether the lens reviewers (which spawn subagents) run inside the chosen runner;
   the docs reportedly say subagents work outside `--bare` (settled by the Phase 0 spike).
3. **Fixer loop** with the cap, the forced-decision path check, the stop conditions, the *Fix
   attempted* comment lines, and note handling.
3b. **Notification email** on confirmed READY and on a loop that stops for the owner.
4. **Plan pickup.** Status field handling and the implementer. Manually triggered first
   ("implement `plan/x.md`"); automatic selection only after the rest is trusted.

## Decisions
Settled by the owner, 2026-10-10:
1. Stage 2 runs in GitHub Actions as a direct `claude -p` call, not the official action.
2. Subscription OAuth token first; switch to an API key if CI runs crowd out interactive use.
3. The owner's login opens PRs and pushes (so workflows trigger). A GitHub App is a later option.
4. Fix-round cap: 3.
5. Plan pickup is explicit ("implement `plan/x.md`") until the rest has run cleanly on a few PRs.
8. The agent moves the PR from draft to ready, right after implementation and a green local gate.
   The owner noted this may move earlier or later if drafts turn out not to hit the triggers; adjust
   then.
9. Email also when the loop stops with only needs-decision findings (or a cap, or a red gate).
12. Review only after the PR leaves draft; email when ready. The reviewer skips drafts.

Settled by the owner, 2026-10-10 (second round):
6. Forced needs-decision paths: the four originals plus credential handling, the runtime schedule and
   job inventory, and `docs/adr/` (all listed under "Forced needs-decision paths").
7. Email delivery: a local job polls PR state; SMTP settings stay on the host. Consequence: the email
   waits if the owner's machine is off.
10. The fixer takes notes that are easy or simply beneficial within the branch's touched scope, and
    leaves the rest with a reason. It does not take follow-ups.
11. The forge interface is a CLI (`scripts/forge`), not an MCP server. "Forge" is the generic term
    for a code-hosting platform (GitHub, GitLab, Gitea); the CLI is our wrapper over whichever one is
    in use. Its name can change if "forge" proves confusing.

Open consequence of 8 and 12 together: the owner learns of a PR only at the READY or stopped email,
not at PR creation. If that is too quiet, add a "PR opened" email.

## Not in scope
- Auto-merge. Merging is the owner's.
- Posting security-class findings.
- Anything that lets the agents edit the standing authorizations or the pipeline's own controls.
