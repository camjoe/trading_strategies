# Plan: agent sandbox follow-ups

Status: blocked on PR #307 and PR #310 merging, and on the owner's yes to each workflow edit in part 1.
Branch to use: `feature/agent-sandbox-followups`, off `develop` after both PRs merge.

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

## Part 2: owner decisions and repository settings (no code)
- Merge #307, then retarget #310 to `develop` (GitHub does this when #307 merges) and mark it ready.
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
