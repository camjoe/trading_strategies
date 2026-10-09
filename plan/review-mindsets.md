# Plan: independent reviews with narrow lenses

Status: designed and piloted 2026-10-09; nothing is built. The design is decided except the items in
"Open decisions". Evidence from the pilot is in the appendices, not in the design.

## Goal and why
Catch what one reviewer with one mindset misses, without making every PR slow or noisy. Same-author
review has limited value: on 2026-10-09 the author found two real bugs in their own reconcile change
only while writing tests. A reviewer that has not seen the author's reasoning, and looks for one kind
of problem, is more likely to find that kind of problem. The pilot (Appendix B) found 12 distinct
defects across two PRs that the author's own review missed.

## Vocabulary
One set of words, used in the skills, the prompts, the PR comment and this plan.

| Term | Meaning |
|---|---|
| **Reviewer** | One read-only agent run with a fresh context. It never sees the author's reasoning. |
| **Lens** | The narrow mindset a reviewer applies. There are four: Break it, Operator, Test skeptic, Simplifier. "Mindset" means lens. |
| **Architecture and conventions** | The fifth reviewer. It applies the repo's layering and style rules rather than a mindset. |
| **Gate** | The deterministic checks (`run_checks`: repo checks, ruff, mypy, layer check, tests). Always first. |
| **Finding** | One defect or gap, after verification and merging duplicates by root cause. Reviewers report `SEVERITY \| path:line \| issue \| scenario`. |
| **Severity** | The only rating scale, used by every reviewer and in the comment: BLOCKER, CONCERN, NOTE. |
| **Pass** | One `pr ready` invocation. The comment says "pass 1", "pass 2". |
| **Verdict** | Scoring a finding after checking it against the code: REAL or NOT REAL. Pilot only: KNOWN (the author had listed it) and MINOR (true but trivial). |

Severity, defined once:
- **BLOCKER**: fix before merge. Books can diverge from the broker, an account can trade twice, money
  moves differently than intended, a guard error is swallowed, or a documented recovery path does harm.
- **CONCERN**: wrong or unsafe in a way that does not move money (an operator misled, a documented
  step that fails, a missing test that hides a bug). Fix in this PR, or decide and say why.
- **NOTE**: optional or follow-up (simplification, placement, a missing safeguard with no bug today).

The old words go away: VIOLATION becomes BLOCKER, and ADVISORY becomes NOTE (or CONCERN if it should be
fixed). Places to rename are in "What changes in the repo". The comment uses the same three words, with
a colour marker: 🔴 Blockers, 🟠 Concerns, 🟡 Notes. Where the owner must choose, the finding carries a
*Decision* line instead of a separate category.

## The reviewers
Each gets only: the diff, the changed files, `AGENTS.md`, and the conventions docs. No author
reasoning, no chat history, no PR description. Read-only; report findings, never fixes. The gate has
already run: reviewers skip anything ruff, mypy, or the layer check reports.

### Architecture and conventions
Applies `docs/architecture/architecture-conventions.md` and the style guides
(`general-style.md`, `python-style.md`, `frontend-style.md`): layering, ownership, placement of
decision logic (side-effect-free logic belongs in `domain/`), timestamp and comment rules, narration.
Runs on every diff except docs-only. No lens covers layering or placement.

### Lens: Break it (adversarial correctness, including money and safety)
Find inputs and sequences that make the change misbehave.
- Failure paths: what if the call raises, times out, returns empty, returns the wrong shape?
- Partial states: crash between two writes, a retry, the same event twice, an event out of order.
- Boundaries: zero, negative, huge, None, empty list, duplicate ids, float vs Decimal.
- State that survives: what is left in the database or at the broker after a failure?
- State from before the change: rows, orders, or logs written by the old code; what happens at
  deploy, and on rollback.
- Shared code: when the change adds behavior to a base class or shared helper, read every other
  implementer and caller, not only the one the change targets. Also read the consumers of any output
  the change alters (status values, artifact fields, log lines, sentinels).

Money and safety probes, applied to any broker, fill, sizing, order, guard, or scheduler path:
- Does any path trade, size, or price differently than the author intended?
- Does a failure fail closed? Is any error swallowed that must propagate
  (`LiveTradingNotEnabledError`, `PaperBrokerAccountMismatchError`, `UnknownBrokerTypeError`)?
- Can books and the broker drift apart (fills not posted, posted twice, posted at the wrong size/price)?
- Anything touching `live_trading_enabled`, `broker_type`, account ids, or credentials.
- Conservation: for any fill or posting path, work two polls with different prices through the code
  and check that posted quantity and posted notional (and commission) sum to the broker's cumulative
  figures. Name the invariant ("books equal broker") and the code that holds it.
- Can an account be traded twice in one day, by a retry, a catch-up, or a re-run?

### Lens: Operator at 3 a.m.
Judge the change by the person who has to find out it broke.
- When this fails, what is the first thing the operator sees? Does the log name the cause?
- Does an alert fire? Which one, to whom? What fails silently (host off, no transport configured)?
- Does the runbook say what to do? Is a doc now stale or wrong?
- Does it add a recurring manual step, and is that step documented and checkable?
- Docs: diff the changed behavior against every runbook and reference doc that describes it,
  including files the PR did not touch. Check that a documented command or grep still finds what the
  runbook says it finds.

### Lens: Test skeptic
Judge whether the tests would catch a regression. The reviewer cannot check the branch out or run
tests; it reasons from the test and the code.
- Would each new test fail if the change were reverted? Walk through it.
- What behavior in the diff has no test? List the paths.
- Do tests assert behavior or only that code ran? Are mocks hiding the real integration?
- Is a test copying the implementation's logic instead of stating the expected result?
- For each behavior gap, say whether it hides a bug (a wrong result today) or only a missing
  safeguard, and name the missing test.

### Lens: Simplifier
Find what can be deleted or made plainer. This repo prefers minimal tooling.
- Code, parameters, flags, or helpers added that nothing needs yet.
- Two ways to do one thing; a new abstraction with one user.
- Defensive code for situations that cannot occur.
- Comments or docstrings that narrate reasoning or history instead of stating facts
  (`docs/conventions/python-style.md`, Comments and docstrings).

## Which reviewers run
`python -m scripts.checks.repo.review_scope_check --base <base_ref>` decides and prints the list.
You can override it: `pr ready: lenses=<names>`.

| Diff touches | Reviewers |
|---|---|
| Docs, skills, maps only | none (the docs check is enough) |
| Ordinary `src/`, API or frontend | Architecture and conventions; Break it; Test skeptic |
| Broker, fill, sizing, order, guard, runtime job, scheduler, database ("aggressive") | the above, plus a second Break it on Opus, plus Operator |
| Large diff or a new module or abstraction | add Simplifier |

Security-class concerns (credentials, authorization, network exposure) go to `/security-review`, not
to a lens. A human reads every PR that touches the broker, sizing, or fill paths; the reviewers inform
that reading. For a risky PR the owner can also run `/code-review ultra` (cloud, billed).

## How to run
1. **Order.** Gate first; a red gate stops everything. Then Architecture and conventions; a BLOCKER
   there stops the lens spend. Then the lenses selected above, in parallel. Then the docs check.
2. **Spawning.** One read-only Sonnet agent per reviewer (the `Plan` agent type has no edit tools),
   given a one-line prompt: read the reviewer's section of `lenses.md` and follow it, with the base
   and head refs. A branch read by ref (a PR on another branch) is never checked out.
3. **Models.** Sonnet for every reviewer. The second Break it on Opus is the only exception. No Haiku
   (Appendix C).
4. **Verification.** The orchestrator opens each reported finding's file and line and runs or reasons
   through its scenario, drops NOT REAL findings, merges duplicates by root cause, and assigns the final
   severity: the highest any reviewer gave, unless verification lowers it with a stated reason.
5. **Tokens.** Each reviewer costs about 60-85k tokens whatever the model, so savings come from
   running fewer: use the table, and on a re-pass run only the reviewers that had findings on the
   touched files. A pre-read bundle of the diff and files costs more and misses cross-file defects.
6. **Prompt** (the reviewer's section follows the line `Lens:`):
```
You are reviewing a pull request through ONE lens: <lens name>. Read-only. Do not edit files.
Inputs: the diff `git diff origin/<base>...<head>`, the changed files, AGENTS.md, and the conventions in docs/.
You have not seen the author's reasoning. Do not assume the change is correct.
Do not read plan/, local/, commit messages, or any PR description.
Lens: <the lens section>
Report each finding exactly as:  SEVERITY | path:line | the issue | the concrete scenario that breaks it
SEVERITY is BLOCKER, CONCERN, or NOTE, as defined in lenses.md.
Rules: no finding without a file and line and a concrete failing scenario. Report a defect once, per
root cause. At most 8 findings, most severe first. Skip anything ruff, mypy, or the layer check
already reports. If you find nothing, say so and list what you checked.
End with: "Files read: <n>" and "Self-assessed confidence: <low|medium|high>".
```

## The PR comment
One comment per PR, created by the first pass and edited in place by every later pass. Replaces the
saved report file. `pr ready` no longer writes `local/pr_readiness_report.md`. The comment needs a PR,
so open it as a draft early; before a PR exists, `pr ready` prints the same content to the terminal.

Layout:
```
<!-- pr-readiness -->
## PR readiness: NOT READY | READY
Reviewed `<sha>` against `<base>` (`<sha>`) · <date> · pass <n> · current | stale (branch has moved)
<one line: n blockers, n concerns, n notes open; n resolved>

### Status
| Step | Result |      Gate, Architecture and conventions, each lens (with its model), docs check.
                        A step that did not run says "not run: stopped at <step>".
### Findings
#### 🔴 Blockers  /  🟠 Concerns  /  🟡 Notes
- [ ] **<n>. <Title>.**
  <the problem: file, line, scenario>
  *Caught by: <reviewers, with their own severity where it differed>*
  *Tests: <do the current tests catch it; the test to add>*      (every defect; not docs or simplification)
  *Pointer: <one-line direction>*  or  *Decision: <owner's recorded choice>*
### How to verify              (open) UI route, command, endpoint, expected behavior, and what is not yet true
<details> Cleanup and obsolescence     classes: safe to remove now, needs targeted verification,
                                       intentional compatibility path, defer/backlog
<details> Resolved                     one line each, with the fixing SHA; oldest dropped first
<details> Pass history and scorecard   passes, commits, reviewers; findings verified REAL / NOT REAL
```

Rules:
- **Status is derived, not ticked.** Each pass re-reads the previous comment, re-verifies every open
  finding against the new HEAD, and moves fixed ones to Resolved. A checkbox you tick is ignored; the
  comment says so.
- **Marker.** The hidden `<!-- pr-readiness -->` line lets a pass find its own comment (`gh api` list,
  then PATCH). Not `--edit-last`, which can hit a different comment.
- **Deterministic rows.** On a checked-out branch the local gate fills them and CI is linked beside
  it. A branch read by ref shows CI only, labelled as such.
- **Public.** The repo is public. Before posting: no local paths, broker account ids, credentials, or
  private strategy parameters. Security-class findings are never posted; they go to `/security-review`
  and the owner is told privately.
- **Length.** About 10-12k characters for the pilot PRs against GitHub's 65,536 limit. Resolved stays
  one line per finding.

### Coverage of the old saved report
| Old report section | In the comment |
|---|---|
| Branch, base, date | Header, plus the reviewed SHA and the current/stale flag |
| Step 1 deterministic table | Status rows (gate); CI linked |
| Steps 2-4 findings (architecture, style, quality) | Status row for Architecture and conventions; findings by severity. Quality is replaced by the lenses |
| Step 5 docs check | Status row; findings by severity |
| Developer Verification Guide | How to verify |
| Cleanup and Obsolescence Review | Cleanup and obsolescence |
| Overall READY / NOT READY | The title line |

Standing authorization (added to `AGENTS.md`, "Standing authorizations", 2026-10-09): `pr ready` may
create and edit this one marker-tagged comment on the branch's own PR without asking. It covers
nothing else: no other comment or review, no labels, no merge.

## What changes in the repo
Built on a branch off `develop`, separate from PRs #294 and #296.
1. **`.ai/skills/code-review/lenses.md`** (new): the reviewers' sections above, the severity
   definitions, the prompt, and a short "why these choices" section distilled from Appendix C.
2. **`.ai/skills/code-review/SKILL.md`**: PR mode becomes one Architecture and conventions section
   (replacing Architecture, Style, Quality), with BLOCKER / CONCERN / NOTE (lines 59-61 use
   VIOLATION, ADVISORY today); a pointer to `lenses.md`.
3. **`.ai/skills/check-pr-readiness/SKILL.md`**: new step list (1 gate, 2 Architecture and
   conventions, 3 lenses, 4 docs check, 5 comment); stop conditions use BLOCKER; the report template is
   replaced by the comment layout; remove "save to `local/pr_readiness_report.md`" (line 72).
4. **`scripts/checks/repo/review_scope_check.py`** and `tests/scripts/test_review_scope_check.py`:
   print the reviewer list; add the money paths it misses today (`src/trading/services/execution/`,
   `src/trading/domain/auto_trading/`, the order and fill repositories; #294 only classified as
   aggressive because it touched `brokers/`); add a diff-size trigger. Update `scripts/README.md` and
   `docs/maps/scripts-map.md`.
5. **`AGENTS.md`**: the `pr code review` and `pr arch review` shortcuts (lines 213-216 describe
   "style + quality" and "architecture"): `pr arch review` runs Architecture and conventions;
   `pr code review` runs the lenses. Add the by-number shortcut for reviewing a PR without checking it
   out. Routing table and skill inventory if wording changes. `.ai/skills/README.md` likewise.
6. **Verify:** `python -m scripts.run_checks repo` (the skills drift check covers the inventory).
7. **Delete this file**; the evidence that must outlive it is in `lenses.md`. The local
   `local/pr_readiness_report.md` (the author-review baseline the pilot compared against) was
   deleted on 2026-10-09; Appendix A keeps its one-line conclusion.

Promote a recurring finding class to a deterministic check when a lens finds it twice. Candidates so
far: a docs-map row that names a changed file; a diff adding more comment and docstring lines than code.
Not built.

## Open decisions
- **READY.** Today: NOT READY while the gate is red or any BLOCKER is open. Whether READY may carry
  open CONCERNs ("ready, 2 to fix") is undecided. Decide later.
- Does a second Sonnet Break it match the Opus one at lower cost? Try on the next aggressive-mode PR.
- Fable: untested (needs usage credits).
- Calibration: after about five PRs, drop or rewrite a lens whose findings are mostly NOT REAL.

---

# Appendix A: how the pilot was run
Two open PRs, both read by git ref and never checked out: #294 (`fix/ibkr-reconcile-order-status`,
orders the open-order list omits) and #296 (`fix/skip-unavailable-ibkr-accounts`, skip accounts whose
IBKR session is down). Round 1: three lenses (Break it, Money and safety, Operator) per PR, six
reviewers. Round 2: Test skeptic and Simplifier, and a model comparison (20 reviewers). Round 3: the
existing Architecture, Style and Quality review. Reviewers were read-only `Plan`-type agents with a
fresh context and were given none of: PR text, commit messages, the author's report, or the list
below. The orchestrator verified every finding by reading the code at the PR head; nothing was run.
The Money and safety lens was later merged into Break it.

Known to the author (scoring baseline, never shown to a reviewer):
- #294: status-path fills carry commission 0.0 and the order's own timestamp; every omitted open row is
  looked up on every run; the looked-up order is matched by id alone; the lookup's `except Exception`
  logs and leaves the order unreported; the list path now reports cumulative state (it used to
  double-post a partial fill); order warnings are still auto-confirmed, now logged; the `0.0001` step
  assumes one contract.
- #296: a session that dies mid-run still fails the run; a run that skips accounts ends `COMPLETE`, so
  the duplicate-run guard blocks a plain re-run (the alert carries `--accounts … --force-run`); a
  persistent outage is a daily `warn` with no escalation (`account-failure-visibility.md` item B); a
  trading-step anomaly in one account still stops the later cap groups (same plan, item A).
The author's readiness report for #294 found no blocker.

# Appendix B: results
**Findings.** Round 1 reported 41 findings: 22 REAL, 10 KNOWN, 9 MINOR, 0 NOT REAL; 25 distinct after
merging duplicates, 12 of them REAL and none on the author's list. Real-finding rate 54% raw, 69%
excluding MINOR. The reviewers raised 5 of the author's 11 listed items, and went past a sixth (the
guard) to the sequence that defeats it.

**Key defects and which runs found them** (✔ found, – missed, · outside the lens):

| Defect | Break it Sonnet | Break it Sonnet, bundle | Break it Opus | Break it Haiku | Money Opus | Money Sonnet | Money Haiku | Operator Sonnet | Operator Haiku |
|---|---|---|---|---|---|---|---|---|---|
| #294 socket double-post | ✔ | – | ✔ | – | ✔ | – | – | · | · |
| #294 delta fill at cumulative price | ✔ | ✔ | ✔ | – | ✔ | ✔ | ✔ | · | · |
| #294 `Filled` with no quantity | ✔ | ✔ | ✔ | – | ✔ | ✔ | – | · | · |
| #296 guard unlock by a failed catch-up | ✔ | – | ✔ | off task | ✔ | ✔ | – | ✔ | – |
| #296 burn-in counts skipped days | ✔ | ✔ | ✔ | off task | – | – | – | · | · |
| #296 broad `RuntimeError` catch | ✔ | ✔ | – | off task | ✔ | ✔ | – | ✔ | – |
| #296 duplicate account names | ✔ | ✔ | ✔ | off task | ✔ | ✔ | – | · | · |
| #296 repair command drops options | ✔ | ✔ | ✔ | off task | – | ✔ | – | ✔ | – |
| #294 unreported order, no cause logged | ✔ | – | – | – | · | · | · | ✔ | ✔ |
| #294 runbook stale | · | · | · | · | · | · | · | ✔ | – |
| #294 two `fill_time` spellings | – | ✔ | ✔ | – | · | · | · | ✔ | – |
| #296 runbook grep misses the WARN line | · | · | · | · | · | · | · | ✔ | ✔ |

Extras verified in round 2: Break it on Opus found orders partly filled before deploy can stick open
(develop's list path wrote cumulative `web-…` fill rows; mechanism verified, occurrence unchecked) and
that a down socket gateway raises `TimeoutError`, which is not skipped. Recall of the first eight
rows: Break it Sonnet 8/8, Opus 7/8, Money Opus 6/8, Money Sonnet 6/8, bundle 6/8, Money
Haiku 1/8, Break it Haiku 0/8.

**Test skeptic and Simplifier.** Test skeptic (Sonnet) found no defect the others missed and
independently flagged the delta price from the test side. Its value is the *Tests* line: it showed
why the current tests pass (a constant test price, hand-built fakes, no sentinel assertion). Simplifier
(Sonnet) found no defects, about eight cleanups, and was the cheapest run.

**Existing review vs the lenses.** The old Architecture, Style and Quality review (one Sonnet agent
per PR) found two of the three key defects on #294 and none of the eight on #296. Its real findings
were all also found by lenses, except two small placement points (Architecture) and a stale docs-map
row (which belongs to the docs check). Hence: drop the Quality step, keep Architecture, merge Style
into it.

**The dry run** rendered both comments (about 10k and 12k characters) and produced the rules in
"The PR comment".

# Appendix C: models and cost
| Reviewer | Model | Tokens (two PRs) | Wall time | Note |
|---|---|---|---|---|
| Break it | Sonnet | 142k | 72 + 80 s | 8/8 key defects |
| Break it | Opus | 225k | 283 + 196 s | 7/8 plus 2 extras |
| Break it | Haiku | 151k | 346 + 162 s | 0/8, one false BLOCKER, one off-task run |
| Money and safety | Opus | 186k | 217 + 157 s | no finding Break it lacked |
| Money and safety | Sonnet | 143k | 68 + 94 s | same recall as Opus |
| Money and safety | Haiku | 163k | 432 + 258 s | "No findings" stated with high confidence |
| Operator | Sonnet | 155k | 81 + 69 s | 4/4 specific items |
| Operator | Haiku | 152k | 187 + 255 s | 2/4; called the `COMPLETE` sentinel a strength |
| Break it, pre-read bundle | Sonnet | 172k | 130 + 89 s | more tokens, missed two defects |
| Test skeptic | Sonnet / Haiku | 147k / 134k | 68-84 s / 193-223 s | Haiku: one false claim per PR |
| Simplifier | Sonnet / Haiku | 125k / 162k | 37-63 s / 185-280 s | Haiku: "no issues" on #294 |
| Architecture and conventions (old three-section review) | Sonnet | 186k (3 sections, 2 PRs) | 67 + 119 s | |

Decisions that follow: Sonnet everywhere; Haiku nowhere (it used as many tokens as Sonnet through
2-4 times the tool calls, and gave two false all-clears); Opus only as a second Break it on
aggressive-mode diffs (every single run missed something, so a second sample covers more than a
bigger model on the same lens); no pre-read bundle; Fable untested. Costs per PR: ordinary diff about
210k (conventions, Break it, Test skeptic); aggressive diff about 400k (adds the Opus Break it and
Operator); Simplifier adds about 60k. Rounds 2 and 3 of the pilot cost about 1.8M tokens, most of it
on the model comparison.

Limits: two PRs, one run per cell, so run-to-run variance is not separated from model and prompt
effects; one scorer, who is also the orchestrator; the old review was tested as a prompt, not as run
in the author's own session. Directional, not conclusive.
