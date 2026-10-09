# Plan: review every PR through several mindsets

Status: drafted 2026-10-09. Nothing is built. Pilot ready to run: see "Pilot kickoff".

## Goal
Catch what one reviewer with one mindset misses, without making every PR slow or noisy. The repo
already has `check-pr-readiness` and `code-review` (Architecture, Style, Quality, plus Standard,
Aggressive, Contract, Cleanup modes). This adds independent, narrow lenses on top, chosen by risk.

## Why
Same-author review has limited value. On 2026-10-09 the author reviewed their own reconcile change and
found two real bugs only while writing tests: a failing lookup would have failed the whole daily run,
and a priceless fill would have closed an order with no fill posted. A reviewer that has not seen the
author's reasoning, and looks for one kind of problem, is more likely to find that kind of problem.

## The five lenses
Each lens gets only: the diff, the changed files, `AGENTS.md`, and the conventions docs. No author
reasoning, no chat history. Read-only. Report findings only; never implement fixes.

### 1. Break it (adversarial correctness)
Find inputs and sequences that make the change misbehave.
- Failure paths: what if the call raises, times out, returns empty, returns the wrong shape?
- Partial states: crash between two writes, a retry, the same event twice, an event out of order.
- Boundaries: zero, negative, huge, None, empty list, duplicate ids, float vs Decimal.
- State that survives: what is left in the database or at the broker after a failure?

### 2. Money and safety
Find ways the change could move money wrongly, hide it, or let the database and the broker disagree.
- Does any path trade, size, or price differently than the author intended?
- Does a failure fail closed? Is any error swallowed that must propagate
  (`LiveTradingNotEnabledError`, `PaperBrokerAccountMismatchError`, `UnknownBrokerTypeError`)?
- Can books and the broker drift apart (fills not posted, posted twice, posted at the wrong size/price)?
- Anything touching `live_trading_enabled`, `broker_type`, account ids, or credentials.

### 3. Operator at 3 a.m.
Judge the change by the person who has to find out it broke.
- When this fails, what is the first thing the operator sees? Does the log name the cause?
- Does an alert fire? Which one, to whom? What fails silently (host off, no transport configured)?
- Does the runbook say what to do? Is a doc now stale or wrong?
- Does it add a recurring manual step, and is that step documented and checkable?

### 4. Test skeptic
Judge whether the tests would catch a regression.
- Would each new test fail if the change were reverted? (Run it, or reason concretely.)
- What behavior in the diff has no test? List the paths.
- Do tests assert behavior or only that code ran? Are mocks hiding the real integration?
- Is a test copying the implementation's logic instead of stating the expected result?

### 5. Simplifier
Find what can be deleted or made plainer. This repo prefers minimal tooling.
- Code, parameters, flags, or helpers added that nothing needs yet.
- Two ways to do one thing; a new abstraction with one user.
- Defensive code for situations that cannot occur.
- Comments or docstrings that narrate reasoning or history instead of stating facts
  (`docs/conventions/python-style.md`, Comments and docstrings).

## Keeping the existing reviews
Architecture, Style, and Quality (`.ai/skills/code-review/SKILL.md`) stay as they are. The lenses add
to them; they do not replace them. The deterministic gate (`run_checks`) always runs first.

## Which lenses run on which PR
Use the repo's own classifier, `python -m scripts.checks.repo.review_scope_check --base <base_ref>`.

| Diff touches | Lenses |
|---|---|
| Docs, skills, maps only | none (Step 5 docs check is enough) |
| Ordinary `src/` change | 1 Break it, 4 Test skeptic |
| Broker adapters, runtime jobs, scheduler, database, sizing, order or fill paths ("aggressive" mode) | 1, 2, 3, 4 |
| Any large diff or a new abstraction | add 5 Simplifier |

A human reads every PR that touches the broker, sizing, or fill paths. The lenses inform that reading.

## How to run
1. Read-only reviewer agents, one per lens, in parallel, each with a fresh context.
2. Each lens prompt lives as its own reference file in the code-review skill folder, one per lens,
   loaded on demand (the skills README describes this layout).
3. `pr ready` gains a step after Step 4: run the lenses the table selects, print their findings, and
   include them in `local/pr_readiness_report.md`. Lens findings use the same severities; a BLOCKER
   from any lens stops readiness.
4. For a risky PR, the user can also trigger `/code-review ultra` (cloud, multi-agent, billed).
5. To reduce correlated errors, run at least one lens on a different model than the author's.

## Prompt template (per lens)
```
You are reviewing a pull request through ONE lens: <lens name>. Read-only. Do not edit files.
Inputs: the diff `git diff origin/<base>...HEAD`, the changed files, AGENTS.md, and the conventions in docs/.
You have not seen the author's reasoning. Do not assume the change is correct.
<paste the lens section above>
Report each finding exactly as:  SEVERITY | path:line | the issue | the concrete scenario that breaks it
SEVERITY is BLOCKER (must fix before merge), CONCERN (should fix or decide), or NOTE.
Rules: no finding without a file and line and a concrete failing scenario. At most 8 findings, most
severe first. Skip anything ruff, mypy, or the layer check already reports. If you find nothing, say so
and list what you checked.
```

## Keeping noise down
- Evidence required: file, line, and a scenario. No guesses.
- Cap at 8 findings per lens. Merge duplicates across lenses before showing them.
- Track outcomes in the PR readiness report: for each finding, real / not real / already known.
  Drop or rewrite a lens whose findings are mostly not real after about five PRs.

## Pilot
Run lenses 1, 2 and 3 on the open work, as independent read-only agents:
- PR #294 (`fix/ibkr-reconcile-order-status`): lookup of orders the open-order list omits.
- PR #296 (`fix/skip-unavailable-ibkr-accounts`): skip accounts whose IBKR session is unavailable and trade the rest.
- PR #293 (sizing step and SMART routing) merged before the pilot could run; review it
  retrospectively against its merge commit `2708d32f` if a second data point is wanted.

Compare with the author's self-review in `local/pr_readiness_report.md`:
- Findings the lenses made that the author missed (the value).
- Findings the author made that no lens made (the gap).
- Proportion of lens findings that were real.
- Cost: time and tokens per lens.

Success: at least one real finding the self-review missed, and a real-finding rate high enough that
reading the output is worth the time. Failure is also a result; record it and adjust the lenses.

## Pilot kickoff (how to run it)
Run from the working copy on branch docs/plan-folder: this file exists only there until PR #295
merges, and the results are recorded in it. The PR branches are read by git ref and are not checked out.

1. `git fetch origin`. Confirm each PR's state with `gh pr view <number> --json state,headRefName`.
   If one has merged, review its merge commit against its first parent instead.
2. Per PR, build the review input: `git diff origin/develop...origin/<branch>` (stat, then full) and the
   changed-file list. The tests are part of the diff.
3. Launch one reviewer per lens (1 Break it, 2 Money and safety, 3 Operator at 3 a.m.) for each PR: six
   reviewers, in parallel. Each is a read-only agent (no Edit or Write tools, for example the Plan agent
   type) with a fresh context. Give each: its lens text from this file, the prompt template, the branch
   ref and the diff command, and an instruction to read `AGENTS.md` and the conventions it names.
   Do NOT give any reviewer: the PR description, the commit messages, the "Known to the author" list
   below, or the author's readiness report.
4. Run lens 2 (Money and safety) on a different model than the orchestrator's, if the agent tool's
   `model` option allows it.
5. Verify every finding before scoring it: open the file and line, then run or reason through the
   scenario. Mark each REAL (a true defect or gap), KNOWN (listed below), NOT REAL (wrong or misread),
   or NOTE.
6. Record the results under "Pilot results": one row per finding (PR, lens, severity, verdict, one
   line), then the real-finding rate, how many REAL findings were new vs KNOWN, and the cost (rough
   time, and tokens if visible).
7. Report to the owner: the value, the gaps (what the author's review found that no lens did), the
   noise, the cost, and a recommendation (adopt, adjust a named lens, or drop). Do not fix findings
   during the pilot; the owner decides which go into #294 and #296.
8. Commit the results to branch docs/plan-folder and push (this updates PR #295).

### Known to the author (score against this; never show it to a reviewer)
PR #294 (reconcile lookup):
- Fills posted from a status reply carry commission 0.0 and the order's own timestamp.
- Every open row the order list omits is looked up on every run; stale rows add one request each.
- A looked-up order is matched by broker order id alone; symbol and side are not compared.
- The lookup's `except Exception` logs and leaves the order unreported.
- The order-list path was changed to report cumulative state (it used to double-post a partial fill).
- IBKR order warnings are still confirmed automatically; they are now only logged.
- The `0.0001` order step is a one-contract assumption (see `contract-trading-rules.md`).

PR #296 (skip unavailable accounts):
- A session that dies during a run still fails the run at the step that notices.
- A run that skips accounts ends with `COMPLETE`, so the duplicate-run guard blocks a plain re-run
  that day; the `warn` alert carries the `--accounts <names> --force-run` command.
- A persistent outage is now a daily `warn` with no escalation (`account-failure-visibility.md`, item B).
- A trading-step anomaly in one account still stops the later cap groups (same plan, item A).

The author's own readiness report for #294 is `local/pr_readiness_report.md` (gitignored). It found no
blocker; its advisories were fixed or are listed above. There is no formal report for #296.

### Kickoff prompt (paste into a fresh session)
```
We are running the multi-lens review pilot. Work in
C:\Users\camer\Documents\Workspaces\repo_copies\trading_strategies on branch docs/plan-folder
(run git checkout docs/plan-folder if you are on another branch). Read AGENTS.md, then
plan/review-mindsets.md in full, especially "The five lenses", "Prompt template", "Pilot",
"Pilot kickoff" and "Known to the author". Review PR #294 (fix/ibkr-reconcile-order-status) and PR #296
(fix/skip-unavailable-ibkr-accounts) against origin/develop with lenses 1, 2 and 3, as independent
read-only reviewer agents that never see the author's reasoning. Read the PR branches by git ref; do
not check them out. Verify and score every finding yourself, record the results under "Pilot results"
in plan/review-mindsets.md, commit and push to docs/plan-folder, then report value, gaps, noise and
cost with a recommendation. Do not fix any finding.
```

## Rollout
1. Review and edit this file (the lens text is the part that matters most).
2. Run the pilot. Record results at the bottom of this file.
3. If it earned its cost: write the five lens reference files, add the step to `check-pr-readiness`,
   update `.ai/skills/README.md` and `AGENTS.md` (skill inventory and the `pr ready` description),
   and run `python -m scripts.run_checks repo` (the skills drift check covers the inventory).
4. Delete this file; the skill files are the record.

## Open questions
- Which lenses matter most to the owner? Order the table accordingly.
- Run lenses in `pr ready` always, or only when asked (`pr ready: deep`)?
- Different model for one lens: which, and is the cost acceptable?
- Where do lens findings live between PR updates: the saved report only, or PR comments?

## Pilot results
(none yet)
