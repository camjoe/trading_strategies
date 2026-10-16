# Plan: agent sandbox follow-ups

Status: blocked on the owner's decision on item 3 and the part 3 items. Items 1, 2, 4, and 5 are done on `feature/agent-sandbox-followups`.
Branch to use: `feature/agent-sandbox-followups`, off `develop`.

## Goal
Finish the items the container work left open. Part 1 edits files the pipeline cannot change on its own
(`.github/workflows/`, a guarded path), so nothing here may be started by `implement-plan`, and each edit
needs the owner's yes with the exact wording stated first (`AGENTS.md`, Standing authorizations).

Background and the decisions behind these items: `docs/reference/agent-sandbox.md`.

## Part 1: workflow edits (each needed the owner's yes)
| # | Change | Why | State |
|---|---|---|---|
| 1 | In `pr-readiness.yml`, run the review agent with `--permission-mode dontAsk --permission-prompts none --strict-mcp-config` | The container agent already runs deny-by-default and ignores a repository's `.mcp.json`; the CI reviewer does neither, so a command outside its allow list is not blocked | Done on `feature/agent-sandbox-followups`: `test_forge_workflow.py` now requires exactly that mode and both flags. The reviewer's allow list was not checked against every command a real pass runs, so read `permission_denials` in the step summary of the first readiness run on this pull request |
| 2 | In `ci.yml` and `security-checks.yml`, add a top-level `permissions: contents: read`, `pull-requests: read` on the `changes` job, and `persist-credentials: false` on each `actions/checkout` | Neither file sets `permissions` or `persist-credentials` today (checked 2026-10-15); `pr-readiness.yml` already does both | Done on `feature/agent-sandbox-followups`: the `changes` job also reads pull requests because `dorny/paths-filter` documents that it needs that on pull-request events. `tests/scripts/test_workflow_permissions.py` pins it |
| 3 | In the `pr-readiness.yml` post job, set `PYTHONPATH` and the working directory once at job level instead of on each step | The same two lines are repeated on four steps of the post job; one missed step runs the forge tool from the wrong place | Not planned, and not decided by the owner. The post job's first step runs before `trusted/` exists, so a job-level default would need an override there, and `test_every_forge_call_runs_from_the_trusted_copy_with_its_source_on_the_path` already pins the failure this guards against. Revisit if a step is ever missed |

Because the review workflow runs `develop`'s copy of `scripts.forge`, a PR that changes these files shows a
red `readiness` check until it is merged. That is expected.

## Part 2: agent rules
| # | Change | Why | State |
|---|---|---|---|
| 4 | Generate `RESTRICTED_SHELL` (`scripts/forge/base.py`) from the allow list in `scripts/forge/local.py` instead of writing it by hand | One source of truth: today the prompt note and `ALLOWED_TOOLS` are kept in step by `test_the_restricted_shell_note_names_exactly_the_commands_the_allow_list_permits` | Done on `feature/agent-sandbox-followups`: `scripts/forge/tools.py` builds `ALLOWED_TOOLS`, `DENIED_TOOLS`, and `RESTRICTED_SHELL` from one set of constants, and the sync test is replaced by tests of the generator. The note now also names `forge check-body`, which was allowed but not mentioned. |
| 5 | Add a tracked `.claude/settings.json` with a baseline of permission rules for interactive sessions | Interactive sessions have no tracked baseline today (`.claude/` holds only an untracked `worktrees` folder, checked 2026-10-15) | Done on `feature/agent-sandbox-followups`: `.claude/settings.json` denies reading `.env` files (not the tracked examples) and force-pushes, and asks before `gh pr merge`, `git reset --hard`, and `git clean`, each for both the `Bash` and `PowerShell` tools. The owner dropped a proposed prompt on every `git push`. `tests/scripts/test_claude_settings.py` pins the shape. |

## Part 3: owner decisions and repository settings (no code)
- `dorny/paths-filter` (the one action not owned by GitHub) is pinned to commit `0e4a8c6` (v3.0.4) in `ci.yml` and
  `security-checks.yml`; Dependabot's monthly `github-actions` run proposes bumps. Replacing it with a
  `git diff --name-only` step, as `pr-readiness.yml` does for the frontend, is still possible if it becomes a
  burden.
- Make `readiness` a required check on `develop` (a repository setting; only the owner can change it).
- Promote `develop` to `main`. The weekly `npm audit` is red on `main` for `source-map-js`, already fixed on
  `develop`.
- Decide when `--agent-container` becomes the default. The recorded plan was after three to five real plans
  have run with it.
- Before any scheduled or triggered run, reconsider the open network and the token in the agent container
  (see "What they do not isolate" in the reference doc).

## Not decided
- Whether the host runner (no `--agent-container`) should also become deny-by-default. The reference doc
  records that only the container agent is.
- Whether the agent's allow list needs to grow if real plans need more commands; the first e2e run had one
  compound command denied and the agent worked around it.

## When this ships
Delete this file and its row in `plan/README.md` in the PR that completes part 1. Move anything still open
in part 2 to the issue tracker or `docs/reference/agent-sandbox.md` first.
