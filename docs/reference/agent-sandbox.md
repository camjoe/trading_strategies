# Agent Sandbox Reference

Type: notes
Status: Active
Created: 2026-10-14
Last Reviewed: 2026-10-15
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
- A deny or allow rule matches the usual form of a command, not every spelling of it (`git -C . push` gets past a
  `git push` rule). Deny-by-default makes that safe for the allow list, and the clone, the stripped environment,
  and the guarded paths still stand behind it.
- Claude Code runs its own set of read-only commands without approval even under `dontAsk` (`echo` and `ls` did in
  a check on 2.1.299), so the allow list does not stop those.
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

## Layers, and which ones today's use needs

The owner judged on 2026-10-15 that the pipeline now does more than the current way of working needs, and chose to
keep it and see how the workflow evolves. Each layer below is a separate piece with its own module and tests, so a
layer can be removed, tightened, or extended without touching the others.

| Layer | Where | Today |
|---|---|---|
| Throwaway clone; the controller imports the agent's commits | `scripts/forge/sandbox.py` (`build_sandbox`) | Core |
| Agent tool allow and deny lists (no push, no `gh`) and the prompt note that names them | `scripts/forge/tools.py` (`ALLOWED_TOOLS`, `DENIED_TOOLS`, `RESTRICTED_SHELL`) | Core |
| Guarded paths: files an unattended run must never change | `scripts/forge/guarded_paths.py` | Core: GitHub runs workflow files from a pushed commit |
| Baseline permission rules for every session in this repository (no `.env` reads, no force-push, a prompt before a merge, a hard reset, or a clean) | `.claude/settings.json` | Useful: also applied to headless runs, which never use project allow rules |
| Gate in a container | `scripts/forge/container.py`, the `gate` stage of `docker/Dockerfile` | Useful: the agent's own tests run without credentials |
| Clone hardening: reset git config and hooks, git without hooks, scrubbed environment | `scripts/forge/sandbox.py` (`harden_clone`, `NO_EXEC_GIT`) | Useful |
| Publish and comment filters for paths, account ids, and credential shapes | `scripts/forge/readiness.py` | Useful against careless text |
| Agent in a container | `scripts/forge/container.py`, the `agent` stage | Beyond today: opt-in |
| Disguise decoding in the filters (hex, base64, reversed, wrapped), terminal escapes, Windows path tricks | `scripts/forge/readiness.py`, `scripts/forge/base.py` (`printable`), `guarded_paths.py` | Beyond today: heuristics against an adversarial agent |
| Scan of the agent's commits for the Claude token | `scripts/forge/local.py` (`outgoing_text`), `readiness.contains_ambient_secret` | Beyond today: the token reaches an agent only with `--agent-container` |

## Where to extend

- **A path the pipeline must never change:** add it to `_EXTRA_GUARDS`, `_DIRECTORY_REASONS`, or `_AGENT_FILES` in
  `guarded_paths.py`, with a case in `tests/scripts/test_forge_guarded.py`.
- **A command the agent may run, or may no longer run:** change the constants in `scripts/forge/tools.py`. The
  allow list, the deny list, and the prompt note follow, and `tests/scripts/test_forge_tools.py` checks they agree.
  The CI reviewer's own list in `pr-readiness.yml` is separate and is pinned by `test_forge_workflow.py`.
- **A rule for every session in this repository:** add it to `.claude/settings.json` with its `PowerShell` twin,
  as a `deny` or `ask` rule only (project allow rules are held back until a folder is trusted and never apply to
  `claude -p`). The file is a guarded path, so a change needs the owner's yes, and
  `tests/scripts/test_claude_settings.py` checks its shape. These rules stop the usual form of a command, not
  every spelling of it (`git -C . push` gets past a `git push` rule).
- **A different code host:** implement the `Forge` protocol in `scripts/forge/base.py`, as `github.py` does for
  `gh`. The loop, the pickup, and the CLI only see the protocol.
- **A different container runtime, or a fake in tests:** pass another `Runner` (the protocol in `container.py`)
  where `docker_runner` is used today.
- **A different agent:** the pickup and the loop take the agent as an injected callable; `local.py` holds the
  Claude Code one and `container.py` the containerized one.
- **Removing a layer:** delete its module code and its tests together, then drop its row above and note the
  decision under "Decisions".

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
- 2026-10-15: the host runner is deny-by-default too, with the options the container uses (shared in `tools.py`),
  so all three runners behave alike. On the host CLI 2.1.299 an unlisted `touch` was refused even without the
  options, so for that version this makes the behavior explicit. The options keep it from depending on the CLI's
  default, which an earlier check on 2.1.296 in the container found to let unlisted commands run.
- 2026-10-15: keep all layers for now, knowing some go beyond today's use; revisit as the workflow evolves.
- 2026-10-15: the CI reviewer runs deny-by-default and ignores a repository's MCP servers, like the container
  agent; `ci.yml` and `security-checks.yml` get a read-only token and drop it after checkout, and the one action
  not owned by GitHub, `dorny/paths-filter`, is pinned to a commit.

## Verified, and not yet

Verified on Windows with Docker Desktop: the gate in a container passes the full suite; a headless agent runs in
the container with only the token; a deny-list session refuses every denied command and writes to `.git/`; two full
`implement-plan` runs with both containers completed on throwaway plans. Not yet verified by a real run on
Linux or macOS (CI runs the Docker-backed tests on Linux).

Checked on 2026-10-15 with the host CLI 2.1.299 (CI pins 2.1.296 and was not re-run) in a scratch repository
with `--permission-mode dontAsk --permission-prompts none`: an `Edit(secrets/**)` deny rule refused the `Write`
tool where the control wrote the file; a `Write` into `.git/hooks` was refused even with no rule, so `.git` is
protected by default; and with `.claude/settings.json` in place `Read(.env)` was refused while
`Read(.env.example)` worked, so the `!` carve-out behaves as the permissions page says.

Follow-up: letting the allow list grow if real plans need more commands.
