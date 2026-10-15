# Plan: agent sandbox follow-ups

Status: blocked on PR #307 merging, and on the owner's yes to each workflow edit in part 1 and to the `.claude/settings.json` contents in part 2.
Branch to use: `feature/agent-sandbox-followups`, off `develop` after #307 merges.

## Goal
Finish the items the container work left open. Part 1 edits files the pipeline cannot change on its own
(`.github/workflows/`, a guarded path), so nothing here may be started by `implement-plan`, and each edit
needs the owner's yes with the exact wording stated first (`AGENTS.md`, Standing authorizations).

Background and the decisions behind these items: `docs/reference/agent-sandbox.md`.

## Part 1: workflow edits (need the owner's yes, one by one)
| # | Change | Why | State |
|---|---|---|---|
| 1 | In `pr-readiness.yml`, run the review agent with `--permission-prompts none` and `--strict-mcp-config` | The container agent already runs deny-by-default and ignores a repository's `.mcp.json`; the CI reviewer does neither, so a command outside its allow list is not blocked | Not started. Check that the reviewer's allow list still covers every command the review skill runs before turning prompts off (unverified) |
| 2 | In `ci.yml` and `security-checks.yml`, add a top-level `permissions: contents: read` and `persist-credentials: false` on each `actions/checkout` | Neither file sets `permissions` or `persist-credentials` today (checked 2026-10-15); `pr-readiness.yml` already does both | Not started. Confirm no job in either file needs a wider permission (unverified) |
| 3 | In the `pr-readiness.yml` post job, set `PYTHONPATH` and the working directory once at job level instead of on each step | The same two lines are repeated on five steps; one missed step runs the forge tool from the wrong place | Not started. `tests/scripts/test_forge_workflow.py` asserts every forge call runs from the trusted copy; update it with the change |

Because the review workflow runs `develop`'s copy of `scripts.forge`, a PR that changes these files shows a
red `readiness` check until it is merged. That is expected.

## Part 2: agent rules
| # | Change | Why | State |
|---|---|---|---|
| 4 | Generate `RESTRICTED_SHELL` (`scripts/forge/base.py`) from the allow list in `scripts/forge/local.py` instead of writing it by hand | One source of truth: today the prompt note and `ALLOWED_TOOLS` are kept in step by `test_the_restricted_shell_note_names_exactly_the_commands_the_allow_list_permits` | Not started. The note names commands by kind (file tools, git verbs, the repository's check commands), so the generator needs a small mapping from tool rules to wording; keep the sentence that a refused command is not a broken shell |
| 5 | Add a tracked `.claude/settings.json` with a baseline of permission rules for interactive sessions | Interactive sessions have no tracked baseline today (`.claude/` holds only an untracked `worktrees` folder, checked 2026-10-15) | Not started. `.claude/` is a guarded path, so the owner approves the exact contents first. Keep it to rules that apply to every session (for example denying a force-push or reading a secrets file); the pickup's strict list stays in code because it only fits unattended runs |

## Part 3: owner decisions and repository settings (no code)
- Decide whether to merge #307 at all: the owner has not yet decided to take this code into `develop`. If it is
  not merged, delete this plan with it.
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
