# Plan: run the pipeline's agents and gate in a container

Status: in progress (branch `feature/docker-agent-sandbox`), started 2026-10-12. PR #301 is merged, so the sandbox,
the controllers, and the guards this plan builds on are on `develop`. Phase 3 and the follow-ups below are done
(PR #306). Phase 1 is built on `feature/docker-gate-container` behind `implement-plan --container`
(`scripts/forge/container.py`, `docker/gate/Dockerfile`), with the `docker/` guard, the `AGENTS.md` wording, and the runbook section; the default flip and
phase 2 are not done.

Branch to use: `feature/docker-gate-container`

## Goal
Close the risk the repository-level sandbox leaves open. Today the unattended agents (`implement-plan`,
`fix-loop`) and the pickup's gate run in a throwaway git clone, but as the owner, on the owner's machine.
Code they write and run (a test, for example) can read the owner's home directory, credential stores, and
`.git/config`, and can reach the network. A container removes the filesystem, environment, and credential
exposure; a network policy limits the rest.

## What exists today (verify before relying on it)
- `scripts/forge/sandbox.py`: `build_sandbox` clones the checkout at a ref, cuts the remote, optionally builds
  a `.venv`; `run_bounded` runs a command with a timeout and kills its process tree.
- `scripts/forge/local.py`: `run_claude_agent(task, model)` starts `claude -p` in the sandbox with a scrubbed
  environment and allow/deny tool lists; `run_gate(base, cwd)` runs `scripts.run_checks pr` with that
  interpreter and environment; `LocalGit` runs the controller's git with hooks and `fsmonitor` off.
- The controllers fetch only commits back from the sandbox (`import_commits`), check them against
  `scripts/forge/guarded_paths.py`, and only then apply and push. That boundary stays as it is.
- Residual risk, as documented in `AGENTS.md` and `docs/runbooks/pr-readiness-workflow.md`: code the agent
  writes and runs executes as the owner.

## Out of scope
- GitHub Actions. The review job already runs on an ephemeral runner; a container adds little there.
- Kubernetes or any scheduler. One owner, one job at a time.
- An MCP server. It changes the agent's tools, not where its code runs.
- Merging, labels, or any new authorization. This plan adds isolation only.

## Design

### Phase 1: the gate in a container
`run_gate` runs `python -m scripts.run_checks pr --base <ref>` inside a container instead of on the host.
- Image: Python 3.14 and the dev requirements baked in (`requirements-dev.txt`, hashed so a change rebuilds
  it). The requirements files are guarded paths, so the agent cannot change what the image needs.
- Mounts: the clean clone the pickup already makes (read-write, because the tests write caches); nothing else.
  No home directory, no owner `.git`.
- Flags: `--network none`, `--read-only` with `--tmpfs` for temp, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, a non-root user, `--memory`, `--cpus`, `--pids-limit`, and the same
  timeout and process-tree kill as `run_bounded`.
- Environment: empty apart from `PATH`, `PYTHONPATH`, and locale. No tokens, no `TRADING_RUNTIME_*`.
- The gate needs no Claude access, so this phase is the simplest and removes "the gate runs the agent's tests
  as the owner".
- Frontend checks need `node_modules`, which the sandbox never had. Keep the current behavior (CI covers
  them) and say so in the result.

### Phase 2: the agents in a container
`run_claude_agent` starts `claude -p` inside a container with the sandbox mounted at a fixed path.
- Image: adds Node and the pinned Claude CLI (`CLAUDE_CODE_VERSION` as in the workflow).
- Credentials: only `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`; the desktop login does not carry
  into a container). It can make model requests only. Unverified: that `claude -p` runs headless in a
  container with this token alone.
- Network: the agent needs `api.anthropic.com`. Two options, to decide: (a) open egress with only the Claude
  token inside, or (b) an allowlisting proxy so only the Anthropic API is reachable. (b) is stronger and
  harder to build on Docker Desktop.
- The agent's tests run in the same container, so a test that exfiltrates would still see the Claude token.
  Accept that (the token is revocable and model-only) or run tests in a second `--network none` container
  the agent cannot start itself (not designed; would need a tool the agent can call).
- Same flags as phase 1 except the network. The tool allow and deny lists stay as a second layer.

### Phase 3: run the forge tool from the base branch in the workflow (done in this branch)
Both jobs of `.github/workflows/pr-readiness.yml` check out the base branch into `trusted` and run every
`scripts.forge` call from there with `PYTHONPATH=src`; the posting job no longer checks out the pull request or
builds a virtual environment. Not covered: the agent step still runs the pull request's scope check, and a pull
request that edits the workflow file itself still runs its own copy (that is how `pull_request` workflows work).

## Steps
1. Spike: build the phase 1 image on the owner's Windows machine (Docker Desktop, WSL2) and run the gate on a
   throwaway clone. Record the time, and whether any test behaves differently on Linux than on the host.
   The CI runner is Linux, so a difference would already show there.
2. Add a `container` module under `scripts/forge/` that builds and runs a container with a timeout, and an
   injected runner so the controllers stay testable without Docker.
3. Switch `run_gate` to it behind a `--container` flag, default off, then default on once it has run for a
   while. Keep the host path as a fallback only if the owner asks for it.
4. Repeat for `run_claude_agent` (phase 2).
5. Add the Dockerfile and its directory to `guarded_paths.py` (an agent must not change its own jail).
6. Update `AGENTS.md` (the standing authorization wording), the runbook (including the workflow's job layout
   after phase 3), and the security notes.
7. Phase 3 after the merge.

## Tests and verification
- Unit tests with a fake container runner: the exact `docker run` arguments, the timeout and kill path, the
  empty environment, and that nothing from the host is mounted.
- Integration tests that need Docker, marked and skipped when it is absent. Inside the container: no host
  file is readable (for example a planted file outside the mount), the environment holds no host variable,
  the network is unreachable for the gate, and a process tree is killed on a timeout.
- A red-team check by hand: plant a `.git/config` entry and a secret-looking variable on the host, run the
  agent with instructions to find them, and confirm neither is visible.

## Decided 2026-10-11 (owner)
- Phase 2 starts with open egress and only the Claude token inside; an allowlisting proxy stays an option if the
  spike or later use shows it is needed. This is a first step, not the final answer.
- The agent's tests run in the same container as the agent for now, so a test the agent writes could read and
  send out the Claude token (revocable, model requests only). The gate is unaffected: it runs in its own
  container with no network and no token.

## Decisions for the owner
1. Open egress or an allowlisting proxy for the agent container (phase 2). Decided above: open egress first.
2. Whether the gate runs in a container by default once it works, or stays opt-in.
3. Whether to keep a host fallback for people without Docker.
4. Approval to change the `AGENTS.md` standing-authorization wording (step 6) and `.github/workflows/pr-readiness.yml`
   (phase 3); both are guarded and need the owner's yes when the work starts.

## Spike results (phase 1, Windows 11, Docker Desktop 29.8.2, WSL2)
Image `python:3.14-slim` (43.5 MB compressed) plus git and `requirements-dev.txt`: 251 MB compressed, 1.06 GB on
disk, about 60 s to build cold. Run with every flag in the phase 1 design.

| Run | Windows host | Container |
|---|---|---|
| `run_checks pr --base origin/develop` (no changed suites) | pass, 17 s | pass, 77 s |
| full suite, `run_suite all --no-cov` | 3518 passed, 45 s | 3518 passed, 99 s |

- No test behaves differently on Linux in the container; the only warnings are the same on both sides.
- The container is 2 to 4 times slower, probably the bind mount to the Windows clone (not confirmed).
- `python:3.14-slim` has no `git`, and the gate shells out to it; the image installs it.
- Git refuses the mount ("dubious ownership"); the image sets `safe.directory /work` in the system gitconfig, so
  the mount point is fixed at `/work` and the environment stays empty.
- `-e .` in `requirements-dev.txt` needs the source tree; the image builds without it and the run puts the clone's
  `src` and `apps` on `PYTHONPATH`.
- A clone under a long path loses deeply nested files on Windows (MAX_PATH) and then looks dirty; the sandbox
  clones under the temp directory, which is short enough on this machine.

## Risks and unverified items
- Docker Desktop on Windows: line endings are fine in the spike; file ownership works with uid 10001. On a
  POSIX host the container runs as the owner's uid so the mount stays writable (untested here).
- Headless Claude CLI authentication in a container with only the OAuth token. Unverified.
- Image size and rebuild time when requirements change. Unverified.
- Docker adds its own attack surface (the daemon runs privileged). Do not mount the Docker socket into any
  container, and keep the flags above.
- A container narrows the host exposure; it does not stop an agent from pushing harmful code that passes the
  guard and the review. The guarded-path list and the owner's review still carry that.

## Follow-ups carried over from PR #301
The merged review ended READY with small notes open. Done in this branch:
- Tests and wiring: `run_pipeline`'s two waits and the gate's base; controller git for `push` (a `pre-push` hook
  does not run), `exists_on`, and the `fsmonitor`/hooks options; the posting job holds the Claude token only in the
  body check; the fake `push` records an explicit phase, not call order.
- `guarded_paths_touched` resolves `.` and `..`, guards absolute paths and paths that leave the repository, and
  pins the short-name rule to the 8.3 shape (`XXXXXX~N.EXT`).
- `email_notifier` reports an `OSError` or SMTP failure while sending, without its message, and returns; any other
  error (an import failure, a bad setting) still propagates.
- One shared message for leftover files; drive-letter paths are matched without catching URL schemes; the
  `findings.verdict` docstring says the title is not the merge decision (counts are).
- A pass over `scripts/forge/` docstrings against the style guide.

Decided, not changed:
- The prompt rule "run `git add` and `git commit` separately" stays a hint. The allow-list matches by prefix and
  cannot express it; the cost of a miss is one lost turn.
- An account-id shape inside a code block still fails the body check: a broker id is a leak wherever it sits.

### Not in this branch
- The email path: set the `TRADING_RUNTIME_ALERT_SMTP_*` variables and run the one-line `email_notifier` check
  (its own branch, as agreed).
- The post-merge smoke test of the fixer round: put a throwaway plan on `develop`, run `implement-plan` with the
  chained fix loop, and remove the plan afterwards.

### Repository settings (owner)
- Make `readiness` a required check on `develop` now that a failed review turns it red.
