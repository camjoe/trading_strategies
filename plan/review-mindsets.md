# Plan: review every PR through several mindsets

Status: drafted 2026-10-09. Nothing is built. Pilot (lenses 1-3 on PR #294 and #296) run 2026-10-09;
results and recommendation under "Pilot results". Lens text and prompt updated from the pilot the
same day; the adjusted lenses 1-3 are untested until they run on another PR.

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
- Shared code: when the change adds behavior to a base class or shared helper, read every other
  implementer and caller, not only the one the change targets.

### 2. Money and safety
Find ways the change could move money wrongly, hide it, or let the database and the broker disagree.
- Does any path trade, size, or price differently than the author intended?
- Does a failure fail closed? Is any error swallowed that must propagate
  (`LiveTradingNotEnabledError`, `PaperBrokerAccountMismatchError`, `UnknownBrokerTypeError`)?
- Can books and the broker drift apart (fills not posted, posted twice, posted at the wrong size/price)?
- Anything touching `live_trading_enabled`, `broker_type`, account ids, or credentials.
- Conservation: for any fill or posting path, work two polls with different prices through the code
  and check that posted quantity and posted notional (and commission) sum to the broker's cumulative
  figures. Name the invariant ("books equal broker") and the code that holds it.

### 3. Operator at 3 a.m.
Judge the change by the person who has to find out it broke.
- When this fails, what is the first thing the operator sees? Does the log name the cause?
- Does an alert fire? Which one, to whom? What fails silently (host off, no transport configured)?
- Does the runbook say what to do? Is a doc now stale or wrong?
- Does it add a recurring manual step, and is that step documented and checkable?
- Docs: diff the changed behavior against every runbook and reference doc that describes it,
  including files the PR did not touch. Check that a documented command or grep still finds what the
  runbook says it finds.

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
5. To reduce correlated errors, run lens 2 on a different model than the author's, only when the diff
   touches broker, sizing, or fill paths. The pilot's Opus run found nothing the same-model lens 1 had
   not, at 2-3 times the time, so it is not worth running elsewhere.

## Prompt template (per lens)
```
You are reviewing a pull request through ONE lens: <lens name>. Read-only. Do not edit files.
Inputs: the diff `git diff origin/<base>...HEAD`, the changed files, AGENTS.md, and the conventions in docs/.
You have not seen the author's reasoning. Do not assume the change is correct.
<paste the lens section above>
Report each finding exactly as:  SEVERITY | path:line | the issue | the concrete scenario that breaks it
SEVERITY is BLOCKER (must fix before merge), CONCERN (should fix or decide), or NOTE.
Rules: no finding without a file and line and a concrete failing scenario. Report a defect once, per
root cause. At most 8 findings, most severe first. Skip anything ruff, mypy, or the layer check
already reports. If you find nothing, say so and list what you checked.
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
- Different model for one lens: settled for now (lens 2, broker/sizing/fill diffs only); revisit
  after lens 2's new conservation probes have run on a few PRs.
- Where do lens findings live between PR updates: the saved report only, or PR comments?

## Pilot results
Run 2026-10-09 from `docs/plan-folder`. PR #294 and #296 both still open. Six read-only `Plan`-type
agents, one per lens per PR, fresh context, launched in parallel; lens 2 ran on Opus, lenses 1 and 3
on the orchestrator's model (Sonnet 5.5). No reviewer was given the PR text, commit messages, the
"Known to the author" list, or the readiness report. Every finding below was checked by reading the
code at the PR head; none was reproduced by running a test. IDs are `<PR>-L<lens>-<n>`; lines are
at the PR head.

Verdicts: REAL (true defect or gap, not disclosed), KNOWN (on the author's list), NOTE (true but
minor, pre-existing, or speculative), NOT REAL (wrong). A dup is the same defect another lens
already reported.

### PR #294 (reconcile lookup)

| ID | Sev | Verdict | Finding |
|---|---|---|---|
| 294-L1-1 | BLOCKER | REAL | `_postable_order` (open_order_reconciliation.py:243-273) synthesizes a `:cum:` fill for any adapter that returns `fills == []` with `filled_qty > 0`, not only IBKR Web. The socket client sets `filled` (orderStatus) and `fills` (execDetails) in separate callbacks (ibapi_client.py:245-290). A poll between them posts the shares as a synthetic fill; the next poll carries the real exec id, which is not in `seen_exec_ids`, and posts them again. Position and cash double. |
| 294-L1-2 | BLOCKER | REAL | The delta fill is priced at the cumulative `avg_fill_price` (:261-271). 5 @ 100 then 5 @ 110 books 5 @ 105 for the second part: cost 1025 against 1050. Permanent drift for any order that fills over more than one poll. |
| 294-L1-3 | BLOCKER | REAL | `_broker_order_from_status` (ibkr_web/adapter.py:282-299) defaults `cum_fill` to 0.0, so a `Filled` reply without it gives FILLED with `filled_qty` 0. `_postable_order` returns it unchanged (`new_qty == 0`) and the row is closed `filled` with no fill posted and never polled again. |
| 294-L1-4 | CONCERN | KNOWN | Looked-up order matched by broker id only; ticker and side not compared. |
| 294-L1-5 | CONCERN | KNOWN | Status-path fill is dated at the order's placement time. |
| 294-L1-6 | CONCERN | REAL | A report below what is recorded, or above it with no price, makes `_postable_order` return None with no log line (:249-259); the order falls into "unreported" indistinguishable from "broker does not know it". |
| 294-L1-7 | CONCERN | KNOWN | One unpaced lookup request per omitted open row on every run. |
| 294-L1-8 | NOTE | NOTE | `sizing.py:44` docstring cut to one line; out of scope for a reconcile fix. |
| 294-L2-1 | BLOCKER | REAL (dup of L1-1) | Same socket double-post, with a worked 10-share example. |
| 294-L2-2 | CONCERN | REAL (dup of L1-2) | Same delta-price defect; notes the tests hold `avg_fill_price` constant across partial fills, which hides it. |
| 294-L2-3 | CONCERN | REAL (dup of L1-3) | Same FILLED-without-quantity defect. The `average_price` "0" posts-at-$0 variant was not verified. |
| 294-L2-4 | CONCERN | KNOWN | Status-path fills carry commission 0 and the order closes, so the fee is never posted. |
| 294-L2-5 | NOTE | KNOWN | Fill dated at placement time; replay order uses `fill_time`. |
| 294-L2-6 | NOTE | KNOWN | Ticker and side not checked (adds the socket-to-web id-reuse scenario). |
| 294-L2-7 | NOTE | NOTE | `submit_order` (ibkr_web/client.py:291-293) sends a sixth confirm POST and then raises even if that reply was the acknowledgement. The loop predates the PR. |
| 294-L3-1 | CONCERN | REAL | A lookup that returns None because of a 503 (`IbWebOrderStatusUnavailableError`) or an unusable reply (no `order_status`/`symbol`) logs nothing (adapter.py:127-133, :236); every such order lands in the generic "not reported by the broker" warning, which now misleads because the broker was asked. |
| 294-L3-2 | CONCERN | REAL | `docs/runbooks/ibkr-paper-trading.md:258-286` still says reconciliation "never sees it again" and that unreported orders are only reported; it does not mention the per-order status lookup, auto-resolution, or the new log line. Only `broker-integration.md` was updated. |
| 294-L3-3 | CONCERN | KNOWN | Commission 0 and placement-time `fill_time` on status-path fills; no marker of which fills were synthesized. |
| 294-L3-4 | CONCERN | KNOWN | Order warnings still auto-confirmed (up to five); now only logged. |
| 294-L3-5 | NOTE | REAL | `order_fills.fill_time` gets two spellings: the list path stores the raw `lastExecutionTime` (`_normalize_fill_time`, adapter.py:~215), the status path stores ISO. Stored timestamps are string-compared (python-style.md, Timestamps). The raw form predates the PR; the PR puts a second form beside it. |
| 294-L3-6 | NOTE | KNOWN | Unbounded sequential lookups, no "looked up N, resolved M, failed K" summary. |
| 294-L3-7 | NOTE | NOTE | Status-reply mapping validated only against a captured payload and a fake gateway; the live-gateway section of the runbook is not updated. |
| 294-L3-8 | NOTE | NOTE (dup of L1-8) | `sizing.py` docstring. |

### PR #296 (skip unavailable accounts)

| ID | Sev | Verdict | Finding |
|---|---|---|---|
| 296-L1-1 | CONCERN | REAL | "Every account unavailable" test is `len(skipped) == len(accounts)` (workflow.py:307); `skipped` is a dict, `resolve_accounts` (job_helpers.py:149-161) does not dedupe. `--accounts a,a` with `a` down: 1 != 2, run proceeds with zero accounts, writes `COMPLETE`, status success. |
| 296-L1-2 | CONCERN | REAL | Partial run writes `COMPLETE`; the guard (`latest_log_contains_sentinel`, job_helpers.py:176-185) reads only the newest log. Operator force-runs the skipped account while the gateway is still down; that run is all-unavailable, fails, writes no `COMPLETE`, becomes the newest log; a later plain run passes the guard and trades the first account a second time. |
| 296-L1-3 | CONCERN | REAL | A skipped-account run is `status: success`. `burn_in_status` counts consecutive success artifacts (latest file per date), so ten days with the IBKR account skipped read `ready_for_live`; before the PR those days were failures. Also, a later failed catch-up run's artifact replaces that day's success. |
| 296-L1-4 | CONCERN | REAL | `except (httpx.TransportError, RuntimeError)` (broker_preflight.py:39) also catches `validate_session`'s account-not-visible and not-enabled-for-trading errors (ibkr_web/client.py:99-111). A wrong or mismatched `account_id` becomes a daily `warn` skip instead of a failed run. Fails closed; the WARN log line does carry the real reason, the alert text does not. |
| 296-L1-5 | NOTE | NOTE | Socket-transport connect failures are likely not caught, so a down TWS still aborts the run. The exception type was not confirmed. |
| 296-L1-6 | NOTE | REAL | The alert's repair command carries only `--accounts`, `--run-source`, `--force-run` (workflow.py:263-264). `--account-trade-caps`, `--primary-accounts`, `--fee`, `--seed`, `--as-of-date` are dropped, so the catch-up uses default caps. |
| 296-L2-1 | BLOCKER | REAL (dup of L1-2) | Same guard unlock; adds that the failure text and runbook tell the operator to "re-run" and that `replay_daily_runs` would also treat the date as missing. |
| 296-L2-2 | CONCERN | REAL (dup of L1-4) | Same broad `RuntimeError` catch. |
| 296-L2-3 | CONCERN | REAL (dup of L1-1) | Same duplicate-name count mismatch. |
| 296-L2-4 | NOTE | NOTE | The test asserting every worker gets only the run account filters on `--accounts` (test_daily_paper_trading_main.py:522-526), so per-account `--account` calls and steps 06/07 are not covered. The code is correct today. |
| 296-L3-1 | BLOCKER | REAL (dup of L1-2) | Same guard unlock; points at ibkr-operations.md:205 ("so a plain re-run works"), which is the sentence that makes it the documented path. |
| 296-L3-2 | CONCERN | KNOWN | `COMPLETE` run reads healthy to `daily_trader_health` and `check_jobs`; only the one-shot `warn` signals it (account-failure-visibility item B). |
| 296-L3-3 | CONCERN | REAL (dup of L1-4) | Same broad `RuntimeError` catch. |
| 296-L3-4 | CONCERN | REAL (dup of L1-6) | Same repair-command defect; adds that `python -m` is not the `.venv` interpreter and `--repo-root` is omitted. |
| 296-L3-5 | CONCERN | REAL | The runbook's log grep (`executed\|Market closed\|COMPLETE\|ERROR`, ibkr-operations.md:159) does not match the new `WARN: skipping ...` line that the table below it lists as the key signal. |
| 296-L3-6 | CONCERN | NOTE | Catch-up step has no deadline or check that it worked, and no market-hours warning. The market-closed case is real but the runbook's log table already gives the `executed N trades` check. |
| 296-L3-7 | NOTE | NOTE | Step 00 details and the `RUN META` line carry the pre-exclusion `caps_summary` and account list. |
| 296-L3-8 | NOTE | NOTE | `skipped_accounts` is absent from the artifact on the all-unavailable failure path; the reasons are only in `error`. |

### Tally
- Raw findings: 41 (PR #294: 23, PR #296: 18). REAL 22, KNOWN 10, NOTE 9, NOT REAL 0.
- Real-finding rate: 22/41 = 54% raw, 22/32 = 69% when NOTEs are excluded. Counting KNOWN as true
  findings (the reviewers could not have known), 32/41 = 78%.
- Distinct findings after merging duplicates: 25. Of those, 12 are REAL and not on the author's
  list: PR #294 six (socket double-post, delta pricing, FILLED with no quantity, unreported with no
  cause logged, stale runbook, mixed `fill_time` spellings); PR #296 six (guard unlock by a failed
  catch-up, burn-in counts skipped days as success, broad `RuntimeError` catch, duplicate
  `--accounts` names, repair command drops run options, runbook grep misses the WARN line).
- New vs KNOWN among REAL: 12 new, 0 already known. Of the 11 items on the author's list, 5 were
  reported by some lens (#294: commission/timestamp, symbol/side, lookup volume, auto-confirm;
  #296: no escalation of a persistent outage). A sixth, the duplicate-run guard blocking a plain
  re-run, was gone past: the lenses found the sequence that defeats the guard.
- By lens: L1 on #294 4 REAL of 8; L2 on #294 3 of 7; L3 on #294 3 of 8; L1 on #296 5 of 6; L2 on
  #296 3 of 4; L3 on #296 4 of 8.
- Overlap: every REAL finding from lens 2 duplicated lens 1 (both PRs). Lens 3's unique REAL
  findings were all documentation or log-visibility (294-L3-1, -2, -5; 296-L3-5). The guard unlock
  was found by all three lenses on #296; the socket double-post by lenses 1 and 2 on #294.
- Gap (5 known items no lens raised): #294 the order-list path reporting cumulative state, the
  `0.0001` one-contract step, the `except Exception` in the lookup (lens 3 checked it and passed
  it); #296 a session that dies mid-run, and a trading-step anomaly stopping later cap groups.
  These are disclosed limitations rather than defects, and the `sizing.py` step is outside the
  diff. The author's readiness report for #294 found no blocker; the lenses found three.

### Cost
- Wall time about 4 minutes for all six in parallel (launched 21:13Z, last finished about 21:17Z).
- Per reviewer: 70-80 s on the orchestrator's model, 157 s and 217 s on Opus (lens 2).
- Tokens (as reported by the harness): about 482k across the six (62k, 76k, 77k, 80k, 89k, 97k),
  90 tool calls. Verification and scoring by the orchestrator (reading code at the PR heads for
  every finding) was not timed; it is the larger cost and does not parallelize.
- Opus on lens 2 cost about 1.2x the tokens and 2-3x the time of the other lenses and found nothing
  the Sonnet lens 1 had not, so the "different model" check bought no extra findings here.

### Limits of this pilot
Two PRs, one scorer who is also the orchestrator, verification by code reading only, and a known
list written after the author's own review. The result is directional.

### Recommendation
Adopt, with adjustments. The success test is met: three BLOCKER-grade defects in #294 and one in
#296, none on the author's list and none in the author's readiness report, at a real-finding rate
above two thirds with no wrong findings.
- Lens 1 (Break it): keep as written. Add one line: "when the change adds behavior to a base
  class or shared helper, read every other implementer and caller" (the socket double-post came
  from that).
- Lens 2 (Money and safety): adjust, do not drop. It duplicated lens 1. Add concrete probes that
  lens 1 does not run: "for any fill path, check that posted quantity and posted notional sum to
  the broker's cumulative figures, across two polls with different prices", and "state each
  invariant (books equal broker) and name the code that holds it". Keep the different-model run
  only for broker, sizing, and fill diffs; it was not worth it elsewhere.
- Lens 3 (Operator): keep. Add "diff the changed behavior against every runbook and reference doc
  that describes it, including files the PR did not touch" (found the stale runbook).
- Prompt: add "report a defect once per root cause" to cut duplicates (41 raw to 25 distinct).
- Run lenses 4 and 5 before rolling out; this pilot did not cover them.
- Owner decisions still open: which of the 12 REAL findings go into #294 and #296. Not fixed here.
