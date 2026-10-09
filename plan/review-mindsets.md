# Plan: review every PR through several mindsets

Status: drafted 2026-10-09. Nothing is built. Pilot not run.

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
- PR #293 (sizing step and SMART routing) merged before the pilot could run; review it
  retrospectively against its merge commit `2708d32f` if a second data point is wanted.

Compare with the author's self-review in `local/pr_readiness_report.md`:
- Findings the lenses made that the author missed (the value).
- Findings the author made that no lens made (the gap).
- Proportion of lens findings that were real.
- Cost: time and tokens per lens.

Success: at least one real finding the self-review missed, and a real-finding rate high enough that
reading the output is worth the time. Failure is also a result; record it and adjust the lenses.

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
