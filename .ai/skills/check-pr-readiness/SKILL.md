---
name: check-pr-readiness
description: Orchestrates the full pre-PR workflow: the deterministic gate, independent fresh-context reviewers chosen by the diff, an advisory docs drift review, and one readiness comment on the pull request that each pass updates. Use when preparing to submit a pull request or when asked to run a PR readiness check.
---

# Checking PR Readiness

Runs six ordered steps. A failure at Steps 1 or 2 stops the pass before any AI spend; a BLOCKER at Step 3 skips the lenses.

| Step | Type | What runs | Stops on |
|---|---|---|---|
| 1 | Deterministic | Gate: `python -m scripts.run_checks pr --base <base_ref>` | Gate still red after `fix checks` |
| 2 | Deterministic | CI status of the PR at HEAD | CI failed |
| 3 | AI | Architecture and conventions reviewer | BLOCKER skips Step 4 |
| 4 | AI | Lenses chosen by `review_scope_check` | — |
| 5 | AI | Docs drift review | Never |
| 6 | Output | The readiness comment on the PR | — |

Reviewers, severities, and how to run and verify them are defined in
[code-review/lenses.md](../code-review/lenses.md). This skill orders the steps and owns the output.

## Invocation

```
pr ready                      # vs develop (default)
pr ready: main                # vs custom base
pr ready: lenses=<names>      # override the reviewers review_scope_check suggests
```

Run it on committed work. The reviewers and the gate's suite targeting read `<base_ref>...HEAD`, so
check `git status --short` first: if tracked files are modified, say so and stop, because the
reviewers would be reviewing code that differs from the working tree.

Run it locally before the first push of a branch, so the unattended pass confirms a branch that is already
clean and the author does not discover findings one pushed pass at a time. A local pass needs no pull request;
it prints the comment text.

When a pull request exists, fetch its context once:

```
python -m scripts.forge review-context [--pr <n>] [--author <login>] [--exclude <check>] [--wait <seconds>] \
    [--expect-sha <sha>] [--max-passes <n>]
```

It prints `pull_request` (number, `head_sha`, `is_draft`, `diff_base_ref`), `previous_comment` (the prior
readiness comment from a trusted author, `null` on a first pass), `previous_pass` (its pass number),
`pass_cap_reached` (when `--max-passes` is set), and `ci` (state of the checks on the head commit). Use `diff_base_ref` as `<base_ref>` and `previous_comment` as the baseline for a later
pass. `--author` names the account that writes the comment (default: the authenticated user);
`--exclude` leaves out the check this pass is itself running in. Comment text from any other author is
never returned.

---

## Step 1 — Gate

```
python -m scripts.run_checks pr --base <base_ref>
```

It runs the enforced docs checks, the repo checks, branch-targeted Python checks, and frontend checks
when the diff touches the frontend: the checks CI enforces.

If it fails once, run `python -m scripts.fix_checks` (safe deterministic fixes only). If that changed
files, show `git diff --stat` and stop: the author reviews and commits the fixes, then runs the pass
again. If nothing changed or the gate is still red, report the exact failing command and output
without paraphrase, and stop. Do not run Steps 3 to 5.

**Unattended in CI.** When the invocation tells you to use `ci` as the gate result or not to run the gate (the
workflow's prompt does), do not run this step or `fix_checks`: the gate runs the pull request's own code, which
must not run in a step that holds the Claude token. Use the context's `ci.state` as the gate result: `pass`
continues to Step 2, `fail` is a red gate (stop as above), and `pending` or `none` is shown as pending.

## Step 2 — CI

If a pull request exists for the branch, compare `git rev-parse HEAD` with `pull_request.head_sha` from
the context. When they match, `ci.state` is the verdict for HEAD (`pass`, `fail`, `pending`, or `none`)
and `ci.checks` names each check. Checks on older commits are never counted.
- `fail`: stop and print the failing check names. The local gate missed something.
- `pending` or `none`: continue and show it as pending; the next pass picks up the result. `--wait`
  holds the context call until checks settle or the time runs out.
- No PR, or the PR head is an older commit: show CI as "not run" in the header and continue.

## Step 3 — Architecture and conventions

Follow [code-review/SKILL.md](../code-review/SKILL.md), PR Mode, as a fresh-context read-only
reviewer on the branch diff. A BLOCKER skips Step 4, and Step 5 still runs.

## Step 4 — Lenses

```
python -m scripts.checks.repo.review_scope_check --base <base_ref>
```

Unattended in CI, run it as `.venv/bin/python -m scripts.checks.repo.review_scope_check --base <base_ref>`. It is the only Python command that step may run.

It prints the reviewers the diff needs (none for a documentation-only diff). Run them in parallel
following "For the orchestrator" in [lenses.md](../code-review/lenses.md): spawn, verify every
finding, merge duplicates, assign severity, and name the test to add in each defect's fix hint. Security-class
findings are routed to `/security-review` and never posted. Each reviewer is a separate fresh-context
subagent; reading the diff yourself does not stand in for one, and an unattended session spawns them
the same way.

**Later passes.** First re-verify every open finding by hand against the new HEAD; that alone can
clear a finding, and READY does not require a fresh reviewer run. Then run the same command on the
incremental diff, `--base <previous reviewed SHA> --head HEAD` (the SHA is in the comment header). Run
the reviewers it suggests only if its list includes the Simplifier, which means the increment changes
200 or more lines outside documentation or adds a source module. Otherwise run none and say so under
Review details. This shortcut applies only after a pass in which the reviewers ran on the whole diff
against the base; if no earlier pass did (for example pass 1 stopped at the gate), run the full-diff
command and its reviewers. This is the accepted trade-off: a small increment is read by the orchestrator while
re-verifying the findings it touches, but no reviewer sees it.

**Fixer lines.** A finding with `*Fix attempted: <sha>, awaiting verification*` is re-verified at the new
HEAD: if the fix holds, tick the box and write `Fixed in <sha>`; if not, leave it open with "still open at
<sha>". Remove the line either way. `*Not fixed: ...*` and `*Left: ...*` lines are copied forward
unchanged unless you disagree, in which case remove the line and say why on the finding.

## Step 5 — Docs drift review

The gate already enforces the mechanical docs checks. This step is judgment: use `docs/maps/docs-map.md`
("Goes stale when") to find the docs that own each changed source file, and check their prose still
matches the code. Report findings with a severity; do not rewrite (the `update-documentation` skill
does that). Never blocks.

## Step 6 — The readiness comment

One comment per PR, created by the first pass and edited in place by every later one, found by its
hidden marker line `<!-- pr-readiness -->`. Authorization to create and edit it is in `AGENTS.md`
("Standing authorizations"); it covers nothing else. With no PR yet, print the same text to the
terminal and do not save a file. Open the PR as a draft early so the comment has a home.

Write the body to a file outside the repo's tracked paths, then:

```sh
python -m scripts.forge comment-upsert --pr <n> --body-file <file>
```

It edits the existing readiness comment in place or creates it, and refuses any body that does not
start with the marker. A later pass takes the previous comment from `previous_comment` in the context,
never from memory.

Layout:

```markdown
<!-- pr-readiness -->
## PR readiness: NOT READY | READY

Reviewed `<sha>` against `<base>` (`<sha>`) · <date> · pass <n> · current | PR head is `<sha>` · Gate ✓ | ✗ <failing command> · CI ✓ <n> of <n> | ✗ <failing checks> | pending | not run

<n> blockers · <n> concerns · <n> notes · <n> tests open · <n> closed. <what is unmet, or the security sentence below>

#### 🔴 Blockers
- [ ] **<n>. <Title>.** `<path>:<line>`: <the problem in plain words, and the steps of the scenario only when the title does not show them>. → <one-line fix, and the test to add when it is a defect> [<reviewers>]

#### 🟠 Concerns
(the same form; "None." when there are none)

<details>
<summary>🟡 Notes (<n> open, optional): one line each</summary>

#### 🟡 Notes (<n>)
- [ ] **<n>. <Title>.** `<path>:<line>`: <the problem in one line>. → <one-line fix> [<reviewers>]

</details>

<details>
<summary>🧪 Tests (<n> open, optional): gaps and extras. The code is not wrong; the tests could say more</summary>

#### 🧪 Tests (<n>)
- [ ] **<n>. Gap: <what is not tested>.** `<path>:<line>`: <what a test would pin>. → <the test to add> [<reviewers>]
- [ ] **<n>. Extra: <what is redundant or brittle>.** `<path>:<line>`: <why>. → <what to remove or merge> [<reviewers>]

</details>

<details>
<summary>✓ Closed (<n>)</summary>

#### Closed (<n>)
- [x] **<n>. <Title>.** Fixed in `<sha>`: <how the fix was verified>.

</details>

### How to verify
<UI route, command, endpoint, expected behavior, and what is not yet true>

<details>
<summary>Review details</summary>

<the reviewers this pass ran and the diff they read; the docs drift result; any step that did not run>
</details>
```

A note or a test item is one line, and a blocker or concern as long as it takes to understand it once: the defect
and its `→` fix hint, in the plain voice below; the fixer's `*Fix attempted*`,
`*Not fixed*`, and `*Left*` lines and the owner's `*Decision*` line each go on their own indented line
directly under the finding. The text after `→` is the
finding's *Pointer*. Leave out `<path>:<line>` for a finding about no one line (a design or a doc outside the
diff). `[<reviewers>]` names who reported it. A severity lowered after verification stays on the finding, in
the lowered tier, with the original and the reason in the tag: `[Break it, rated CONCERN; lowered to NOTE because
CI is the backstop]`.

**Plain voice.** Write each finding the way you would say it to the owner across a desk: common words, short
sentences, one idea in each. Say what is wrong, where, and what to do. Leave out hedges ("may", "could
potentially"), stacked clauses, and anything the title or `path:line` already says. If a scenario has steps, list
them as short bullets under the finding, not in one long sentence. If the owner would have to reread it, cut it
down.

Before: `A failed same-day catch-up can still change the burn-in result. burn_in_status.py:129-131: the day's
status comes only from the latest artifact, while anomalies, kill switches and traded accounts are combined
across the day. (a) The scheduled run fails at step 08 after orders went out, then --accounts x --force-run
succeeds: the day counts as success. (b) Per-account sim,ibkr: sim traded cleanly, then the ibkr catch-up
fails (status: failed); sim is judged failed and its streak resets. The new test covers only a catch-up that
succeeds.`

After: `A failed catch-up for ibkr also fails sim for the day, though sim traded fine. burn_in_status.py:129: the
day takes its status from the newest artifact only. → Judge failure per account.`

A finding about the tests alone goes under Tests, titled `Gap:` (a missing case, a mutation that would survive,
a weak assertion) or `Extra:` (two tests that repeat each other, a redundant or brittle test). It is a NOTE at
most and never makes the title NOT READY. If the code is wrong today, whether or not a test would catch it, report
the defect in its usual tier and name the test to add after its `→`. Tests items are fixed and closed like notes.

A closed finding (fixed, or covered by a *Decision*) keeps its number, goes under Closed, and shrinks to one
line with its box checked: `- [x] **<n>. <Title>.** Fixed in `<sha>`: <how the fix was verified>.` A finding
covered by a *Decision* says `Decided` instead of `Fixed`. When a *Decision* exists, it replaces the finding's
`*Not fixed*` or `*Left*` line.

Standard phrases for a step that did not run, in Review details: "not run: stopped at <step>" when the pass
stopped early, and "not re-run: incremental diff below the threshold" for reviewers a later pass skipped.

"current" means the reviewed SHA equals the PR head at the moment of writing. A comment cannot update
itself, so a later push makes it stale until the next pass; readers compare the SHA in the header with
the PR head. When the local HEAD is not pushed, the header says `PR head is <sha>`.

Title: READY only when the gate is green, CI has not failed, no BLOCKER is open, every open
CONCERN is fixed or carries a *Decision*, and the reviewers `review_scope_check` suggests for the whole
diff have run in this pass or an earlier one. Otherwise NOT READY, and the line under the header says what
is unmet (for example "2 concerns need a fix or a Decision"). The title carries no counts.

Security-class findings are never posted and do not decide the title. Say once, in the line under the header,
whether the owner has recorded a *Decision* on the security review (a finding in the previous comment whose
*Decision* line covers the security review). If one is
recorded, say nothing more about security. If none is, add "run /security-review before merge" to that line.
The title follows the rules above only.

A *Decision* is the owner's. The owner states it in the session; that pass writes it onto the finding's
*Decision* line, and every later pass copies it forward from the previous comment unchanged. It exists
nowhere else, so it survives only if each pass copies it. No pass ever writes one on its own.

Everything else is re-derived from the code. Each later pass re-reads the previous comment and
re-verifies every open finding against the new HEAD. Finding numbers never change across passes: a
new finding takes the next number, and a fixed one keeps its number.

A box is checked only by a pass that has verified the fix at HEAD (or that a *Decision* covers). An
owner's tick is re-verified, not trusted: if the finding is fixed it stays checked; if not, the pass
unchecks it and says "unchecked: still open at <sha>". Drop a closed finding two passes after the pass
that closed it (closed in pass 2, dropped in pass 4) to keep the comment short.

If the gate is red and a PR exists, still update the comment: the header shows `Gate ✗ <failing command>`,
Review details says "not run: stopped at gate", and there are no findings.

Before posting, remove local machine paths, broker account ids, credentials, and private strategy
parameters; the repository is public.

---

## Constraints

- Do not run AI steps if Step 1 fails or Step 2 shows a failed check.
- Do not implement fixes. Report only.
- Do not review unchanged files.
- Post only the marker-tagged comment; no other comment, review, label, or merge.
- Never post security-class findings; route them to `/security-review` and tell the owner privately.
- Cleanup notes are advisory unless they identify a directly related obsolete path with safe removal evidence.

## Repo references

- `scripts/run_checks.py`
- `scripts/checks/pr.py`
- `scripts/checks/repo/review_scope_check.py`
- `docs/architecture/architecture-conventions.md`
- `docs/conventions/general-style.md`
- `AGENTS.md`
