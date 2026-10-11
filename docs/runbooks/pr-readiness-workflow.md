# PR Readiness Workflow

Type: runbook
Status: Active
Created: 2026-10-10
Last Reviewed: 2026-10-10
Purpose: Operate the GitHub workflow that runs `pr ready` on pull requests and keeps the readiness comment current.
Related: [Runbooks Index](README.md), [Check PR Readiness skill](../../.ai/skills/check-pr-readiness/SKILL.md), [Scripts Map](../maps/scripts-map.md)

`.github/workflows/pr-readiness.yml` runs the `pr ready` shortcut on every non-draft pull request into
`develop` and creates or edits the single `<!-- pr-readiness -->` comment. It is not a merge gate:
a failed run leaves the check red and posts nothing.

## How a pass runs

1. Checks out the pull request head and builds the repo-local `.venv`.
2. Reads the pull request, the previous readiness comment from `github-actions[bot]`, and CI state
   with `python -m scripts.forge review-context`. It waits until the same checks are seen twice (its
   own `readiness` check is excluded), fails if the head moved since the event, and fails if the pass
   cap is reached.
3. Runs the agent with the Claude token and **no GitHub token**. It writes the comment body to a file.
4. Runs `python -m scripts.forge check-body`, which refuses a body that lacks the marker, whose pass
   number is not the previous one plus one, or that holds a runner path or credential-like text.
5. Posts it with `python -m scripts.forge comment-upsert`, which writes only the readiness comment.

Drafts, fork pull requests, and Dependabot pull requests are skipped.

## One-time setup

```bash
claude setup-token
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

The token draws on the Claude plan's usage limits. A leaked token is a credential in a public
repository's secrets; rotate it at expiry (one year) or on any suspicion.

## Repository variables

| Variable | Default | Effect |
|---|---|---|
| `READINESS_MAX_PASSES` | `8` | Stop reviewing a pull request after this many passes |
| `READINESS_CI_WAIT_SECONDS` | `1500` | How long a pass waits for CI before reviewing |
| `READINESS_SAVE_TRANSCRIPT` | unset | `true` uploads the scrubbed agent transcript as a 7-day artifact, to diagnose reviewer behavior |

```bash
gh variable set READINESS_SAVE_TRANSCRIPT --body true
```

## When a run fails

| Symptom | Cause |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN is not set` | The secret is missing |
| `The agent run reported an error` | Expired or rejected token, or the agent failed; read the step log |
| `The agent did not write a comment body` | The agent finished without writing the body file; re-run |
| `contains a local path` / `a forbidden string` / `credential-like text` | The comment would have leaked a runner path or token; nothing was posted |
| `--forbid-env variable is not set or empty` | The token variable was missing from the check step, so the leak guard would check nothing |
| `Readiness pass cap reached` | `READINESS_MAX_PASSES` passes already ran; the job fails so a stale comment is not mistaken for current. Raise the variable or review by hand |
| `a newer push landed` | The head moved after the event; the newer push starts its own pass |
| `Cannot read the pass number` | The previous comment has no `· pass N ·` header; fix or delete the comment |
| `The header should say pass N` | The agent wrote the wrong pass number; nothing was posted, re-run |

Re-run a failed pass from the Actions tab, or push a commit. A newer push cancels an older pass.

## Running the fixer loop

`python -m scripts.forge fix-loop --pr <n>` runs on your machine, not in GitHub. Start it from the pull
request's branch with a clean working tree, signed in to `claude` and `gh`. Each round it:

1. reads the readiness comment and stops if it says READY (no open blocker or concern) or nothing is left that
   a fixer can do;
2. starts a headless `claude -p` session (model `sonnet` unless `--model` says otherwise) that follows the
   `fix-pr-readiness` skill, commits locally, and writes a new comment body to a file;
3. checks the round: every committed path (renames count as a delete and an add) and every uncommitted or
   untracked file is compared with the guarded list in `scripts/forge/guarded_paths.py`, and files git
   ignores that tools run (under `.venv/`, `.claude/`, env files, `sitecustomize`) are checked for changes
   since the round began; a guarded path or any uncommitted leftover undoes the round and stops. Files git
   ignores cannot be restored automatically, so a changed one stops the round and the detail names it for you to
   inspect;
4. refuses the new body unless it only adds status lines (the round's commits are dropped), then posts it and
   pushes `HEAD` to the pull request's branch by name; if the push fails the comment is restored and the round
   undone;
5. waits up to 45 minutes for the next review pass.

A stopped round leaves the checkout as it was before the round, so the next run can start. Every ending,
including a failure, sends the email.

The agent is a guardrail, not a sandbox. It runs without GitHub tokens or any secret-looking variable, with an
empty git configuration (no credential helper), only git's `file` transport, and an empty `gh` configuration,
so a push or a `gh` call fails even from a test it writes. Its tool permissions also allow only the
repository's checks and test runner as Python, deny `gh` and the git verbs that push, reset, clean, or change
configuration, and deny writes under `.git/`. It still runs on your machine under your account, can read your
files, and the gate then runs what it wrote, so the boundary you rely on is the loop's own check of what the
round changed. Treat the readiness comment as untrusted text.

When the comment says READY and the branch claimed a plan with `implement-plan`, the loop first removes that
plan file and its index row in one pushed commit, then waits for the docs-only pass that confirms READY. Only
then does it finish and email you. A plan the branch did not claim is never touched.
It stops after three rounds. At the end it emails the pull request link, the verdict, and the open
counts through the `TRADING_RUNTIME_ALERT_SMTP_*` settings (no email is sent if they are unset).
Run it only where you are comfortable with the agent editing files under your account.

If a round stops, the checkout is restored to where the round began; read the email or the printed detail for
why. If a push fails the comment is restored too, and if even that fails the detail says the comment still
claims a fix that did not land.

## Picking up a plan

`python -m scripts.forge implement-plan --plan plan/<file>` also runs on your machine, from a clean
working tree, signed in to `claude` and `gh`. It refuses a plan that is not in the plan index, is already in
progress or blocked, or lists dependencies (pass `--depends-ok` once they are satisfied). Then it:

1. creates the plan's branch off `origin/develop` and commits the claim (the plan's Status line and its
   index row);
2. pushes the branch and opens a **draft** pull request;
3. starts a headless `claude -p` session (model `sonnet` unless `--model` says otherwise) that follows the
   `implement-plan` skill, commits locally, and may write questions and a summary to files;
4. pushes the commits, runs the pull-request gate itself, and checks the paths the work touched.

By default the command then waits up to 30 minutes for the review's first comment and runs the fixer loop
(below) on the pull request, so one command takes a plan to READY or to the point that needs you, and you get
one email at the end. `--no-fix` stops once the pull request is ready; `--max-rounds`, `--review-wait-minutes`
and `--wait-minutes` set the fixer's limits. The review only runs on pull requests into `develop`, so with
another `--base` pass `--no-fix`. The loop trusts the readiness comment from `github-actions[bot]` and from you.

The pickup refuses a plan that is not on the base branch, so push or merge a new plan first. The agent runs in
the same restricted environment as the fixer's, and any uncommitted leftover, guarded path, or changed ignored
file keeps the pull request a draft; uncommitted leftovers are discarded, and the commits are pushed to the draft
so you can review them. If the claim fails, the checkout goes back to the branch you started on and the local
branch is removed; the detail gives the command to delete the remote branch if it got there.

The pull request leaves draft, which starts the review, only when the agent made commits and raised no
question, the gate passed, and no guarded path was touched. Otherwise it stays a draft and the command
says why. `--no-ready` always leaves it a draft. The plan file stays in the branch; it is removed when the
work is ready to merge.

## Pin and upgrade the agent

The workflow installs a pinned Claude Code version (`CLAUDE_CODE_VERSION` in the workflow). Upgrade it
deliberately and compare one pass before and after.
