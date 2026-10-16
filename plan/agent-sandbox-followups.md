# Plan: agent sandbox follow-ups

Status: blocked on evidence. Every code item is done on `feature/agent-sandbox-followups`; what remains is the owner's call on `--agent-container` as the default, after three to five real plans.
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
| 3 | In the `pr-readiness.yml` post job, set `PYTHONPATH` and the working directory once at job level instead of on each step | The same two lines are repeated on four steps of the post job; one missed step runs the forge tool from the wrong place | Done on `feature/agent-sandbox-followups` (the owner chose to implement it): the post job sets `PYTHONPATH` and the working directory once. Its first step overrides the directory because `trusted/` does not exist yet. `test_forge_workflow.py` checks the effective values and that only that step overrides |

Because the review workflow runs `develop`'s copy of `scripts.forge`, a PR that changes these files shows a
red `readiness` check until it is merged. That is expected.

## Part 2: agent rules
| # | Change | Why | State |
|---|---|---|---|
| 4 | Generate `RESTRICTED_SHELL` (`scripts/forge/base.py`) from the allow list in `scripts/forge/local.py` instead of writing it by hand | One source of truth: today the prompt note and `ALLOWED_TOOLS` are kept in step by `test_the_restricted_shell_note_names_exactly_the_commands_the_allow_list_permits` | Done on `feature/agent-sandbox-followups`: `scripts/forge/tools.py` builds `ALLOWED_TOOLS`, `DENIED_TOOLS`, and `RESTRICTED_SHELL` from one set of constants, and the sync test is replaced by tests of the generator. The note now also names `forge check-body`, which was allowed but not mentioned. |
| 5 | Add a tracked `.claude/settings.json` with a baseline of permission rules for interactive sessions | Interactive sessions have no tracked baseline today (`.claude/` holds only an untracked `worktrees` folder, checked 2026-10-15) | Done on `feature/agent-sandbox-followups`: `.claude/settings.json` denies reading `.env` files (not the tracked examples) and force-pushes, and asks before `gh pr merge`, `git reset --hard`, and `git clean`, each for both the `Bash` and `PowerShell` tools. The owner dropped a proposed prompt on every `git push`. `tests/scripts/test_claude_settings.py` pins the shape. |

## Part 3: owner decisions and repository settings (no code)
- Decided 2026-10-15: `readiness` stays a check that does not block merges into `develop`. It goes red on any PR that
  changes `scripts/forge` (the review runs `develop`'s copy), so requiring it would block those PRs. Revisit after a
  few clean passes. Making it required is a repository setting only the owner can change.
- Decided 2026-10-15: promoting `develop` to `main` is not part of this work. The weekly `npm audit` is red on `main`
  for `source-map-js`, which `develop` already fixes.
- Decided 2026-10-15: `dorny/paths-filter` (the one action not owned by GitHub) stays, pinned to commit `0e4a8c6`
  (v3.0.4) in `ci.yml` and `security-checks.yml`; Dependabot's monthly `github-actions` run proposes bumps. Replacing
  it with a `git diff --name-only` step, as `pr-readiness.yml` does for the frontend, is possible if it becomes a
  burden.
- Decided 2026-10-15: the host runner is deny-by-default too (`tools.DENY_BY_DEFAULT_OPTIONS`), like the container
  and the CI reviewer. The first real pickup on the host shows whether the allow list needs to grow.
- Open: `--agent-container` stays opt-in until three to five real plans have run with it; the owner then decides
  whether it becomes the default.
- Open: before any scheduled or triggered run, reconsider the open network and the token in the agent container
  (see "What they do not isolate" in the reference doc).

## Not decided
- Whether the agent's allow list needs to grow if real plans need more commands; the first e2e run had one
  compound command denied and the agent worked around it.

## When this ships
Delete this file and its row in `plan/README.md` once the open items above are decided or moved to
`docs/reference/agent-sandbox.md`. The owner asked to keep it until the work is complete.
