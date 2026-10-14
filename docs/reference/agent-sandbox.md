# Agent Sandbox Reference

Type: notes
Status: Active
Created: 2026-10-14
Last Reviewed: 2026-10-14
Purpose: Explain where the plan pickup, the fixer loop, and the gate run, what the Docker containers isolate and what they do not, how the images are built, and the decisions behind them.
Related: [PR Readiness Workflow Runbook](../runbooks/pr-readiness-workflow.md), [Scripts Map](../maps/scripts-map.md)

The plan pickup (`python -m scripts.forge implement-plan`) and the fixer loop (`fix-loop`) run on the owner's
machine. The operating steps live in the runbook; this note records what the isolation does and why it is built
this way.

## Where each step runs

| Step | Where | Notes |
|---|---|---|
| The agent (`claude -p`) in the pickup and each fixer round | The owner's machine by default; a Docker container with `--agent-container` | Works in a throwaway clone either way. |
| The gate (`scripts.run_checks pr`) after the pickup pushes | A Docker container by default; the owner's machine with `--no-container` | Runs the branch's tests, including ones the agent wrote. |
| The readiness review and the comment posting | GitHub's own runners | Never uses Docker; the forge tool runs from the base branch. |

Before a plan is claimed, the command checks that Docker works, builds a missing image, and (for the agent)
that the token is set, so a missing Docker or token stops the run with nothing opened on GitHub.

## What the containers isolate

- **Both containers:** only the clean clone is mounted, at `/work` (the agent also gets the directory holding the
  files its prompt names, at `/exchange`); read-only root, all capabilities dropped, `no-new-privileges`, a
  non-root user, and memory, CPU, and process limits; a short list of environment variables and no host secrets.
- **The gate container** has no network and no credentials.
- **The agent container** has an open network and one credential, `CLAUDE_CODE_OAUTH_TOKEN`. It runs the CLI with
  `--permission-mode dontAsk --permission-prompts none` (anything outside the allow list is denied) and
  `--strict-mcp-config` (a repository's MCP servers are ignored).

## What they do not isolate

- Code the agent runs inside its container can read the token and, with the open network, send it out. The owner
  accepted this: the token only makes model requests, and the owner does not intend to revoke it. A host-side
  credential proxy, or running the agent's tests in a second container with no network and no token, would
  close it; reconsider before any scheduled or triggered run.
- The tests the agent writes run in the same container as the agent.
- Docker's daemon is privileged. The Docker socket is never mounted into a container.
- A container does not stop an agent from pushing harmful code that passes the guard and the review. The
  guarded-path list and the owner's review still carry that.
- On the host runner and in the CI reviewer the CLI is not deny-by-default: a command outside the allow list is
  not blocked there, only the deny list is.
- A relative directory symlink made inside a container on a Windows bind mount cannot be read or deleted by
  Windows. The agent entrypoint removes the one `python -m venv` makes. The symlink tests run only on Linux.

## Controller hardening that applies with or without Docker

- `harden_clone` resets a clone's git configuration and hooks before the controller runs git there, and the
  controller's git runs with hooks and `fsmonitor` off and without secret-looking environment variables.
- The agent's summary, questions, and comment files are read only when they are plain files; a link or
  directory holds the commits like a guarded path.
- The agent's commits (whole patch, binary files, authors, committers, messages) are scanned for the Claude token
  before they are applied or pushed; a hit is held locally.
- Text the agent wrote is shown on the terminal with control characters as escapes.
- The guarded paths include the files a later `claude -p` run loads (`.mcp.json`, `CLAUDE.md`, `AGENTS.md` at any
  depth, `.claude/`, `.vscode/`, `.devcontainer/`) and `docker/`, so an agent cannot change its own sandbox.
- The publish filters refuse more credential shapes, more forms of a user-profile path, and the token in several
  encodings. They are heuristics against careless text, not against an adversarial agent.

## How the images are built

`docker/Dockerfile` has two stages that the runner builds with `--target`: `gate` (Python 3.14, git, the dev
requirements, a non-root user) and `agent` (the gate plus Node and the pinned Claude Code, with an entrypoint
that makes `/work/.venv` and starts `claude`). The images are built locally from the owner's checkout, never from
the agent's clone. The tag is a hash of the Dockerfile and the requirements (and, for the agent, the pinned
version), so an image is built once and reused; a normal run spends under a second checking for it. Base images
are pinned by tag, not by digest, and a newer base image does not trigger a rebuild.

The Claude Code version is pinned in two places that must match: `scripts/forge/container.py` and
`.github/workflows/pr-readiness.yml`. A test fails when they differ.

## Decisions

- 2026-10-12: open egress for the agent container first; the allowlisting proxy stays an option.
- 2026-10-12: the agent's tests run in the same container as the agent for now.
- 2026-10-14: one reused `claude setup-token` token; no revocation planned.
- 2026-10-14: the gate container is the default; the agent container stays opt-in until it has run on three to
  five real plans.
- 2026-10-14: deny-by-default applies to the container agent only; the host runner and the CI reviewer are
  follow-ups.

## Verified, and not yet

Verified on Windows with Docker Desktop: the gate in a container passes the full suite; a headless agent runs in
the container with only the token; a deny-list session refuses every denied command and writes to `.git/`; two full
`implement-plan` runs with both containers completed on throwaway plans. Not yet verified by a real run on
Linux or macOS (CI runs the Docker-backed tests on Linux).

Follow-ups: the CI reviewer's `--permission-prompts none` and `--strict-mcp-config`; explicit `permissions` and
`persist-credentials: false` on `ci.yml` and `security-checks.yml`; job-level `PYTHONPATH` and working directory in
the readiness post job; letting the allow list grow if real plans need more commands.
