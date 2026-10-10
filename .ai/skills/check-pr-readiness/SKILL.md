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

## Step 2 — CI

If a pull request exists for the branch, compare `git rev-parse HEAD` with the PR head
(`gh pr view --json number,isDraft,headRefOid,url`). When they match, `gh pr checks` reports on that
commit, but it does not show which commit; to confirm a CI run exists for HEAD, list runs with
`gh run list --branch <branch> --json headSha,name,status,conclusion` and look for `headSha` equal to
HEAD. Judge only runs for HEAD; a cancelled or superseded run on an older SHA is ignored.
- A failed check: stop and print the failing job names and links. The local gate missed something.
- Pending checks, or no run for HEAD yet: continue and show them as pending; the next pass picks up
  the result.
- No PR, or the PR head is an older commit: show "not run" in the status table and continue.

## Step 3 — Architecture and conventions

Follow [code-review/SKILL.md](../code-review/SKILL.md), PR Mode, as a fresh-context read-only
reviewer on the branch diff. A BLOCKER skips Step 4, and Step 5 still runs.

## Step 4 — Lenses

```
python -m scripts.checks.repo.review_scope_check --base <base_ref>
```

It prints the reviewers the diff needs (none for a documentation-only diff). Run them in parallel
following "For the orchestrator" in [lenses.md](../code-review/lenses.md): spawn, verify every
finding, merge duplicates, assign severity, and add each defect's *Tests* line. Security-class
findings are routed to `/security-review` and never posted.

**Later passes.** First re-verify every open finding by hand against the new HEAD; that alone can
clear a finding, and READY does not require a fresh reviewer run. Then run the same command on the
incremental diff, `--base <previous reviewed SHA> --head HEAD` (the SHA is in the comment header). Run
the reviewers it suggests only if its list includes the Simplifier, which means the increment changes
200 or more lines outside documentation or adds a source module. Otherwise run none and say so in the
status table. This is the accepted trade-off: a small increment is read by the orchestrator while
re-verifying the findings it touches, but no reviewer sees it.

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
gh api repos/{owner}/{repo}/issues/<n>/comments --paginate \
  --jq '.[] | select(.body | startswith("<!-- pr-readiness -->")) | .id'   # existing comment id
gh pr comment <n> --body-file <file>                                       # none yet: create
gh api -X PATCH repos/{owner}/{repo}/issues/comments/<id> -F body=@<file>  # exists: edit
```

Layout:

```markdown
<!-- pr-readiness -->
## PR readiness: NOT READY | READY

Reviewed `<sha>` against `<base>` (`<sha>`) · <date> · pass <n> · current | PR head is `<sha>`

<n blockers, n concerns, n notes open; n closed>

🔴 **Blocker**: fix before merge · 🟠 **Concern**: fix in this PR, or the owner records a Decision · 🟡 **Note**: optional or follow-up.

### Status
| Step | Result |
|---|---|
| 1 Gate | ✓ / ✗ <failing command> |
| 2 CI | ✓ / ✗ / pending / not run |
| 3 Architecture and conventions | <counts> |
| 4 <each lens, with its model> | <counts> |
| 5 Docs drift review | <counts> |
| Open findings (later passes) | re-verified by hand |

Standard phrases for a step that did not run: "not run: stopped at <step>" when the pass stopped
early, and "not re-run: incremental diff below the threshold" for reviewers a later pass skipped.

### Findings
#### 🔴 Blockers  (then 🟠 Concerns, 🟡 Notes)
- [ ] **<n>. <Title>.**

  <the problem: file, line, scenario>

  *Caught by: <reviewers, with their own severity where it differed>*

  *Tests: <do the current tests catch it; the test to add>*      (every defect; not docs or simplification)

  *Pointer: <one-line direction>*   or   *Decision: <the owner's recorded choice and reason>*

A NOTE may take one line: `- [ ] **<n>. <Title>.** <problem> *Caught by: <reviewers>*`, with a
*Tests* line only when the note is a defect.

A closed finding (fixed, or covered by a *Decision*) keeps its number and its tier, goes after the
open ones, and shrinks to one line with its box checked: `- [x] **<n>. <Title>.** Fixed in `<sha>`: <how the fix was verified>`. A finding
covered by a *Decision* is checked the same way, and its line says `Decided` instead of `Fixed`.

### How to verify
<UI route, command, endpoint, expected behavior, and what is not yet true>

<details><summary>Cleanup and obsolescence</summary>
Each item classed: safe to remove now / needs targeted verification / intentional compatibility path / defer/backlog.
</details>

<details><summary>Pass history and scorecard</summary>
| Pass | Commit | Reviewers | Open (blockers / concerns / notes) |
A pass that ran no reviewers says so: `| 3 | <sha> | none (open findings re-verified by hand) | 0 / 0 / 10 |`
Findings verified: REAL n, NOT REAL n, MINOR n.
</details>
```

The scorecard counts only findings that reviewers newly reported in that pass. A pass that ran no
reviewers reports 0, and re-verifying a finding already in the comment is not counted.

"current" means the reviewed SHA equals the PR head at the moment of writing. A comment cannot update
itself, so a later push makes it stale until the next pass; readers compare the SHA in the header with
the PR head. When the local HEAD is not pushed, the header says `PR head is <sha>`.

Title: READY only when the gate is green, CI has not failed, no BLOCKER is open, and every open
CONCERN is fixed or carries a *Decision*. Otherwise NOT READY, and the line under the title says what
is unmet (for example "2 concerns need a fix or a Decision"). The title carries no counts.

A *Decision* is the owner's. The owner states it in the session; that pass writes it onto the finding's
*Decision* line, and every later pass copies it forward from the previous comment unchanged. It exists
nowhere else, so it survives only if each pass copies it. No pass ever writes one on its own.

A severity lowered after verification stays on the finding, in the lowered tier, with the original
and the reason on the *Caught by* line: `*Caught by: Break it (rated CONCERN; lowered to NOTE because
CI is the backstop)*`.

Everything else is re-derived from the code. Each later pass re-reads the previous comment and
re-verifies every open finding against the new HEAD. Finding numbers never change across passes: a
new finding takes the next number, and a fixed one keeps its number.

A box is checked only by a pass that has verified the fix at HEAD (or that a *Decision* covers). An
owner's tick is re-verified, not trusted: if the finding is fixed it stays checked; if not, the pass
unchecks it and says "unchecked: still open at <sha>". Drop a closed finding two passes after the pass
that closed it (closed in pass 2, dropped in pass 4) to keep the comment short.

If the gate is red and a PR exists, still update the comment: the gate row red, the rest "not run:
stopped at gate", no findings.

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
