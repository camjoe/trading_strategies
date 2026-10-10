# Plan: automated plan → PR → readiness → fix pipeline

Status: drafted 2026-10-10, under discussion. Nothing built. Branch: `plan/agent-pipeline-automation`.
Decisions 1-5, 8, 9, 12 are settled (see "Decisions"); 6, 7, 10, 11 are to be re-asked after the
owner reviews the current text. Edit this file until they are closed.

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
   runs one command (for example `python -m scripts.pipeline review --pr <n>`). Everything else is
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
| `anthropics/claude-code-action` supports `pull_request` (opened, synchronize, ready_for_review, reopened), `issue_comment`, `schedule` | reported, recheck |
| The action skips draft and closed PRs | reported; applies with an explicit prompt? **unconfirmed** |
| Same-repo PRs work; fork PRs get no secrets | reported |
| Subscription auth: `claude setup-token` (one-year OAuth token) passed as `claude_code_oauth_token` | reported supported for Pro, Max, Team, Enterprise |
| Subscription token does not work with `--bare` | reported |
| Normal (non-bare) mode loads `CLAUDE.md`, `.ai/skills/`, and subagents, so lens reviewers can run | reported |
| Subscription usage limits and how CI runs share them with interactive use | **not documented**; inference only |
| GitLab integration is beta, authenticates by API key, Bedrock, or Vertex (no subscription token listed), and mention triggers need a webhook listener | reported |
| Claude Code on the web scheduled routines need a claude.ai login and suit scheduled work, not PR events | reported |

Everything marked reported or unconfirmed is verified by a small spike before Phase 2 is built:
a throwaway workflow on a test PR that runs the reviewer step as a direct CLI call with the
subscription token, and records what posts, which skills and subagents load, how it behaves on
`ready_for_review` vs `synchronize`, and what it costs against the plan's limits. The official
action's draft behavior is no longer on the critical path (decisions 1 and 12); test it only if we
later want the action.

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
0. **Verification spike** (see "Verified vs unverified"): subscription token in Actions with a direct
   CLI call, subagents and skills in the runner, behavior on ready_for_review and synchronize, and
   cost per review. Nothing else is built until this is read.
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

To re-ask after the owner reviews this text:
- 6. Is the forced needs-decision path list complete? (Proposed additions: `.env*` and credential
  handling, the runtime schedule and job inventory, `docs/adr/`.)
- 7. Email delivery: local job polling PR state (SMTP stays on the host), or repository secrets and a
  workflow step?
- 10. Is "easy or simply beneficial, within the branch's touched scope" the right bar for the
  fixer's notes, or should it also take follow-ups?
- 11. Forge interface as a CLI in `scripts/forge` (recommended) or an MCP server?

Open consequence of 8 and 12 together: the owner learns of a PR only at the READY or stopped email,
not at PR creation. If that is too quiet, add a "PR opened" email.

## Not in scope
- Auto-merge. Merging is the owner's.
- Posting security-class findings.
- Anything that lets the agents edit the standing authorizations or the pipeline's own controls.
