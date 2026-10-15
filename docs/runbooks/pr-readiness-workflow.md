# PR Readiness Workflow

Type: runbook
Status: Active
Created: 2026-10-10
Last Reviewed: 2026-10-15
Purpose: Operate the GitHub workflow that runs `pr ready` on pull requests and keeps the readiness comment current.
Related: [Runbooks Index](README.md), [Check PR Readiness skill](../../.ai/skills/check-pr-readiness/SKILL.md), [Scripts Map](../maps/scripts-map.md), [Agent Sandbox Reference](../reference/agent-sandbox.md)

`.github/workflows/pr-readiness.yml` runs the `pr ready` shortcut on every non-draft pull request into
`develop` and creates or edits the single `<!-- pr-readiness -->` comment. It is not a merge gate:
a failed run leaves the check red and posts nothing.

## How a pass runs

The `readiness-review` job:

1. Checks out the pull request head and builds the repo-local `.venv`, then checks out the base branch into a
   separate `trusted` directory. Every `scripts.forge` call in both jobs runs from that copy, so the code that
   holds a token is never code from the pull request. A pull request that changes `scripts/forge` is not
   exercised by this workflow until it is merged; CI tests it.
2. Reads the pull request, the previous readiness comment from `github-actions[bot]`, and CI state
   with `python -m scripts.forge review-context` (from the `trusted` copy). It waits until the same checks are seen twice (its
   own `readiness-review` and `readiness` checks are excluded), fails if the head moved since the event,
   and fails if the pass cap is reached.
3. Runs the agent with the Claude token and **no GitHub token**. The job's permissions are read-only. The agent
   may run `git`, `cat`, `ls` and the scope check only: not the gate, pytest or any other code from the pull
   request, because that code would run with the Claude token in its environment. CI is the gate result it
   reports. It writes the comment body to a file, and
   that file is the only thing handed on, as an artifact.

The `readiness` job, which starts only if the first succeeded:

4. Checks out only the base branch into `trusted` (this is the only job with `pull-requests: write`; it never
   checks out the pull request and needs no virtual environment, so nothing the agent wrote in its working tree
   or `.venv` is present), and fetches the body artifact.
5. Runs `python -m scripts.forge check-body`, which refuses a body that lacks the marker, whose pass
   number is not the live comment's plus one, or that holds a runner path, a user-name path, an account-id shape,
   or credential-like text. In example paths `<user>`, `<username>`, `<name>` and `<segment>` may stand in for a
   user name; any other name, bracketed or not, is refused.
6. Confirms the pull request head is still the commit that was reviewed, and fails without posting if a
   push landed meanwhile.
7. Posts it with `python -m scripts.forge comment-upsert`, which writes only the readiness comment. This
   is the only job with the GitHub token.

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

A pass is two jobs. Problems before and during the agent show on `readiness-review`; the `readiness` job then
fails with "The readiness-review job ... nothing was posted" so the required check is red, not skipped.
Problems with the body, the head check, or the post show on `readiness`.

| Symptom | Cause |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN is not set` | The secret is missing |
| `The agent run reported an error` | Expired or rejected token, or the agent failed; read the step log |
| `The agent did not write a comment body` | The agent finished without writing the body file; re-run |
| `contains a local path` / `a forbidden string` / `credential-like text` | The comment would have leaked a runner path or token; nothing was posted |
| `--forbid-env variable is not set or empty` | The token variable was missing from the check step, so the leak guard would check nothing |
| `Readiness pass cap reached` (on `readiness-review`) | `READINESS_MAX_PASSES` passes already ran; the job fails, and `readiness` goes red with it, so a stale comment is not mistaken for current. Raise the variable or review by hand |
| `The pull request head moved` (on `readiness`) | A push landed during the review; nothing was posted and the newer push starts its own pass |
| `a newer push landed` | The head moved after the event; the newer push starts its own pass |
| `Cannot read the pass number` | The previous comment has no `· pass N ·` header; fix or delete the comment |
| `The header should say pass N` | The agent wrote the wrong pass number; nothing was posted, re-run |

Re-run a failed pass from the Actions tab, or push a commit. A newer push cancels an older pass.

## Running the fixer loop

`python -m scripts.forge fix-loop --pr <n>` runs on your machine, not in GitHub. Start it from the pull
request's branch with a clean working tree, signed in to `claude` and `gh`. Each round it:

1. reads the readiness comment and stops if it says READY (no open blocker or concern) or nothing is left that
   a fixer can do;
2. builds a **sandbox**: a throwaway clone at the pull request's head with its own virtual environment (about
   45 seconds with a warm pip cache), whose remote points nowhere, so it cannot push;
3. starts a headless `claude -p` session in the sandbox (model `sonnet` unless `--model` says otherwise) that
   follows the `fix-pr-readiness` skill, commits there, and writes a new comment body to a file;
4. fetches the sandbox's commits into your repository without checking them out (refused unless they descend
   from where the round began), and compares every changed path (renames count as a delete and an add) with
   the guarded list in `scripts/forge/guarded_paths.py`; a guarded path, or any uncommitted change left in the
   sandbox, discards the round;
5. refuses the new body unless it only adds status lines; otherwise fast-forwards your branch to the fetched
   commits (refused if they do not descend from where the round began), posts the body, and pushes `HEAD` to
   the pull request's branch by name; if the comment or the push fails, the branch is put back (and a posted
   comment is restored);
6. deletes the sandbox, and waits up to 45 minutes for the next review pass.

Your checkout is untouched until step 5, and only commits that passed the path check ever reach it. Whatever else
the agent wrote in the sandbox (hooks, git configuration, files git ignores, the sandbox's `.venv`) is deleted with
it and is never run by the loop's own steps (the pickup's gate does run the branch's tests; see "Picking up a plan"). Every ending, including a failure, sends the email.

**What the sandbox does not do.** It isolates the repository, not the machine. The agent still runs as you, can
read your files, and code it writes and runs (a test, for example) can reach the rest of your filesystem and the
network. Its environment withholds GitHub tokens and secret-looking variables, git reads an empty configuration
with no credential helper and only the `file` transport, and `gh` reads an empty configuration directory, so a
push or a `gh` call fails even from a test it writes. Its tool permissions also deny `gh` and the git verbs that
push, reset, clean, or change configuration. Treat the readiness comment as untrusted text, and run the loop
only on plans and pull requests you are comfortable having the agent act on. The loop's own git commands in your checkout run with hooks and `fsmonitor` off, so a hook the agent writes there does not run when the loop merges or commits; a git setting it changes in your `.git/config` still can, so real isolation (a container, WSL, or a separate OS user) is the stronger protection.

The sandbox has no `node_modules`, so a change under the frontend cannot pass the frontend checks there; CI
checks those.

When the comment says READY and the branch claimed a plan with `implement-plan`, the loop first removes that
plan file and its index row in one pushed commit, then waits for the docs-only pass that confirms READY. Only
then does it finish and email you. A plan the branch did not claim is never touched. The loop stops after three
rounds. At the end it emails the pull request link, the verdict, and the open counts through the
`TRADING_RUNTIME_ALERT_SMTP_*` settings (no email is sent if they are unset).

If a push fails the comment is restored and the branch put back, and if even the restore fails the detail says
the comment still claims a fix that did not land.

## Picking up a plan

`python -m scripts.forge implement-plan --plan plan/<file>` also runs on your machine, from a clean
working tree, signed in to `claude` and `gh`. It refuses a plan that is not in the plan index, is already in
progress or blocked, lists dependencies (pass `--depends-ok` once they are satisfied), or is not on the base
branch (push or merge a new plan first). Then it:

1. creates the plan's branch off `origin/develop` (or `--base`) and commits the claim (the plan's Status line and
   its index row);
2. pushes the branch and opens a **draft** pull request;
3. builds a sandbox at the claim commit and starts a headless `claude -p` session in it (model `sonnet` unless
   `--model` says otherwise) that follows the `implement-plan` skill, commits there, and may write questions
   and a summary to files;
4. fetches the commits into your repository and checks the paths they touched. If any is guarded, nothing is
   pushed or applied (GitHub runs a workflow file from a pushed commit): the commits are kept under the local
   ref `refs/forge/held/<branch>/<commit>`, and the detail says so, for you to inspect with `git diff`. Otherwise it applies
   them and pushes them to the draft, and records the summary and questions in the pull request description;
5. runs the pull-request gate in a second, clean clone of the pushed commit, with the interpreter that runs
   this command rather than the sandbox's `.venv`, so it tests exactly what was pushed. The gate runs the
   branch's tests, which are code the agent wrote, as you but with the agent's scrubbed environment (no tokens or
   SMTP settings); it never runs in your checkout. It needs the dev requirements
   installed in the environment you start the command from. Uncommitted work
   left in the sandbox keeps the pull request a draft.

The agent runs in the same restricted environment as the fixer's. The pull request leaves draft, which starts the
review, only when the agent made commits and raised no question, no guarded path was touched, and the gate
passed; otherwise it stays a draft and the command says why. `--no-ready` always leaves it a draft. If the claim
fails, the checkout goes back to the branch you started on and the local branch is removed; the detail gives the
command to delete the remote branch if it got there. The plan file stays in the branch; it is removed when the
work is ready to merge. The claim branch is pushed without an upstream, so a manual `git pull` on it needs the
remote named (`git pull origin <branch>`).

**What an unattended run cannot change.** `scripts/forge/guarded_paths.py` holds the full list. For
planning, note that all of `scripts/` is guarded, because the workflow imports from it with a token in hand,
as are `src/common/__init__.py` and any `sitecustomize.py`, `usercustomize.py` or `.pth` file. Files that a
later `claude -p` run loads as instructions or tool servers are guarded at any depth: `.mcp.json`, `CLAUDE.md`,
`CLAUDE.local.md`, `AGENTS.md`, and anything under a `.claude/` directory; so are `.vscode/` and `.devcontainer/`.
A plan whose work includes a file under `scripts/` (a data-operations helper, for example) is therefore held or
undone, never pushed; do that part by hand or in a session you run yourself.

By default the command then waits up to 45 minutes for the review's first comment and runs the fixer loop
(above) on the pull request, so one command takes a plan to READY or to the point that needs you, and you get
one email at the end. `--no-fix` stops once the pull request is ready (then run `fix-loop` yourself if you want
another `--max-rounds`); `--wait-minutes` sets how long it waits for each review pass, the first included. The
review only runs on pull requests into `develop`, so with another `--base` pass `--no-fix`. The loop trusts the
readiness comment from `github-actions[bot]` and from you.

### Running the gate in a container

`implement-plan` runs step 5 in Docker by default; `--no-container` runs it with your interpreter instead. It
needs Docker running (Docker Desktop with the WSL2 backend on Windows). Before it claims the plan, the command
checks that Docker works and builds the image if it is missing, so a missing or stopped Docker stops the run with
nothing opened on GitHub. The container has no network and sees only the clean clone and a short list of
environment variables, never your tokens or files. What it isolates, and what it does not, is in the
[Agent Sandbox Reference](../reference/agent-sandbox.md).

The image (`trading-gate:<hash>`, the `gate` stage of `docker/Dockerfile`) is built from your checkout's Dockerfile
and requirements, never the agent's clone, and rebuilt when either changes. A newer base image or Debian package
does not trigger a rebuild: remove the image (`docker image rm trading-gate:<hash>`) to pick one up. A gate that
outlives its one-hour limit is red and its container is killed by name. The frontend checks do not run in the
container (it has no Node); CI runs them.

### Running the agent in a container

`--agent-container` (on `implement-plan` and `fix-loop`) runs the agent in Docker as well; it is opt-in until it has
run on several real plans. Set the token in the shell you start the command from, typing it so it is not written to
a file, a profile, or a settings `env` block:

```powershell
$env:CLAUDE_CODE_OAUTH_TOKEN = Read-Host "token"   # a token from `claude setup-token`; do not paste it into chat
python -m scripts.forge implement-plan --plan plan/<file> --agent-container
```

Without the variable the command stops with a message before it claims the plan. The agent container has an open
network and that token is the one credential inside it, so code the agent runs can read it and send it out; the
[Agent Sandbox Reference](../reference/agent-sandbox.md) records that risk. The tool prints the token as `<token>`
if the agent echoes it.

The image `trading-agent:<hash>` is the `agent` stage of the same Dockerfile. It is about 2 GB, builds on first use,
and rebuilds when its Dockerfile, the gate requirements, or the pinned Claude Code version change. Inside the
container a command outside the agent's allow list is denied; on the host it is not blocked.

If a sandbox is left behind with "could not be deleted", the agent made a relative symlink to a directory on the
Windows mount (the `lib64` link that `python -m venv` makes, for example), which Windows cannot read or delete. The
entrypoint removes that one link. Remove the sandbox from a container:
`docker run --rm --entrypoint rm -v <parent>:/p <image> -rf /p/repo`, where `<parent>` is the directory that holds
`repo` and `<image>` is any `trading-agent` image.

## Pin and upgrade the agent

The agent's Claude Code version is pinned in two places that must match: `CLAUDE_CODE_VERSION` in
`.github/workflows/pr-readiness.yml` and `CLAUDE_CODE_VERSION` in `scripts/forge/container.py`. A test
(`test_the_pinned_version_is_the_one_the_workflow_installs`) fails when they differ, and the agent image rebuilds
when the pin changes. Upgrade both deliberately and compare one pass before and after.
