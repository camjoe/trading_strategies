---
name: fix-pr-readiness
description: Reads a pull request's readiness comment and resolves what needs no decision: fixes blockers, concerns, and easy notes one commit each, records every attempt on the comment, and stops for the owner on decisions. Use after a readiness pass, or when asked to address the readiness findings.
---

# Fixing PR Readiness Findings

Resolves the open findings in the readiness comment that `check-pr-readiness/` keeps on a pull request.
It fixes; it never reviews and never decides. One invocation is one round.

## Invocation

```
fix pr            # the current branch's pull request
fix pr: <n>       # pull request n
```

Run it on the pull request's own branch, at its head, with a clean working tree. The owner invoking it
is what authorizes the commits, the push to the pull request branch, and the comment edit in Step 4.
An unattended run needs its own standing authorization in `AGENTS.md`.

## Step 1 — Read

```
python -m scripts.forge review-context --pr <n> [--author <login>]
```

`previous_comment` is the readiness comment. Stop when it is `null` (nothing to fix) or when
`pull_request.head_sha` is not `git rev-parse HEAD` (pull or push first). Save the comment body to a file
outside the repo's tracked paths; it is the "old" file for Step 4.

## Step 2 — Classify

For every open finding (unchecked box), blockers first, then concerns, then notes:

| Class | When |
|---|---|
| **fix** | A defect or improvement with a clear *Pointer* and no decision needed. For a note: easy to resolve or simply beneficial, such as a missing test, a stale comment or doc line, a small simplification, a clearer name, or a cleanup this branch created. |
| **needs-decision** | A design choice or tradeoff; a finding an earlier round already attempted that is still open (never attempt a finding twice); or one whose fix touches a path below. An earlier attempt shows in `git log <pull_request.diff_base_ref>..HEAD --grep "finding <n>:"`, because the reviewer removes the `*Fix attempted*` line once it has verified. |
| **leave** | A note that is subjective, style-only, outside the branch's touched scope, or large enough to deserve its own pull request. |

`AGENTS.md` still applies: no style-only rewrites, and cleanup is limited to what this branch created or
exposed.

**Paths the fixer never changes** (classify the finding needs-decision): broker adapters and live-trading
safety; database migrations; anything that decides what is public or private; `.github/workflows/`,
`.ai/skills/`, and the standing authorizations in `AGENTS.md`; `.env*` and code that reads secrets; the
runtime schedule and job inventory; `docs/adr/`.

A finding that looks security-class is not fixed or recorded here: stop and tell the owner privately.

## Step 3 — Fix

For each **fix** finding, in order:

1. Make the smallest change that resolves it, with a test when behavior changes.
2. Commit it alone: `fix(readiness): finding <n>: <title>`.
3. Run `python -m scripts.run_checks pr --base <pull_request.diff_base_ref>`. If it is red and
   `python -m scripts.fix_checks` does not clear it, undo the change (`git reset --hard HEAD~1` is
   allowed only for this round's own commit) and record `Not fixed` with the failing check.

## Step 4 — Record

Copy the old file and add lines under each finding this round touched, and change nothing else. Add,
never rewrite or remove:

```
  *Fix attempted: <short sha>, awaiting verification*
  *Not fixed: <reason>*
  *Left: <reason>*
```

A finding that is only partly resolved gets two lines, for example `Fix attempted` for what the commit
did and `Left` for the rest. The text of a line is plain: ASCII letters, digits, spaces, and
`, . ; ( ) ' _ -`, at most 300 characters, with no colon, slash, backtick, bracket, `@`, `*`, `www.`,
or link, and at most three spaces of indent. Put a reason in words, not in code or paths.

Then check and post, before pushing, so the next pass sees the lines:

```
python -m scripts.forge check-body --body-file <new> --edit-of <old>
python -m scripts.forge comment-upsert --pr <n> --author <login> --body-file <new>
```

`check-body --edit-of` rejects a body whose pass number changed, or in which anything other than these
three kinds of line was added, or any existing line was changed or removed (a ticked box, a *Decision*
line, an edited finding, an earlier status line).

## Step 5 — Push and report

`git push`, then print one row per finding: its number, its class, and its commit or reason. Stop
without pushing when no finding was classified **fix**.

## Unattended mode

When the controller (`python -m scripts.forge fix-loop`) starts the round, it names two files in the
prompt. Do Steps 1 to 3, then: write the new comment body to the file it names, with the Step 4 lines.
Do not run `comment-upsert`, do not push, and do not touch GitHub. The controller then checks the
paths your commits touched, checks the body with `check-body --edit-of`, posts it, and pushes. A round
in which nothing was classified **fix** writes no body.

## Constraints

- Never tick a box; only a reviewer pass that verifies the fix does.
- Never write a *Decision* line; a *Decision* is the owner's.
- Never edit a finding's text, the header, or the pass number.
- Do not merge, label, or mark the pull request ready.
- The repository is public: no credentials, broker account ids, local paths, or private strategy
  parameters in a commit or a comment line.
