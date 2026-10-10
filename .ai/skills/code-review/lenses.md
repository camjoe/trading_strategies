# Reviewers and Lenses

Independent, read-only reviews of a diff. Each reviewer is one agent run with a fresh context that
has not seen the author's reasoning. Four of them apply a narrow mindset, called a lens; the fifth
applies the repo's architecture and style rules. `python -m scripts.checks.repo.review_scope_check
--base <base_ref>` prints which reviewers a diff needs.

Sections: [Vocabulary](#vocabulary) · [Rules for every reviewer](#rules-for-every-reviewer) ·
[Architecture and conventions](#architecture-and-conventions) · [Break it](#break-it) ·
[Operator](#operator) · [Test skeptic](#test-skeptic) · [Simplifier](#simplifier) ·
[For the orchestrator](#for-the-orchestrator) · [Why these choices](#why-these-choices)

A reviewer reads "Vocabulary", "Rules for every reviewer", and its own section only.

## Vocabulary

| Term | Meaning |
|---|---|
| **Reviewer** | One read-only agent run with a fresh context. |
| **Lens** | A narrow mindset: Break it, Operator, Test skeptic, Simplifier. "Mindset" means lens. |
| **Gate** | The deterministic checks (`python -m scripts.run_checks pr --base <base_ref>`). They have already passed; reviewers skip anything they report. |
| **Finding** | One defect or gap, after verification and merging duplicates by root cause. |
| **Severity** | The only rating scale: BLOCKER, CONCERN, NOTE. |
| **Verdict** | Scoring a reported finding against the code: REAL, NOT REAL (wrong or misread), or MINOR (true but trivial or not actionable; dropped and counted separately). |
| **Decision** | The owner's recorded choice on a finding, with the reason: accept it, defer it, or reject it. Only the owner makes one; no reviewer or orchestrator invents it. |
| **Pass** | One `pr ready` invocation. |

**BLOCKER**: fix before merge. Books can diverge from the broker, an account can trade twice, money
moves differently than intended, a guard error is swallowed, or a documented recovery path does harm.

**CONCERN**: wrong or unsafe in a way that does not move money (an operator misled, a documented step
that fails, a missing test that hides a bug). Fix it in this PR, or the owner records a Decision. An
open CONCERN with neither keeps the PR from READY.

**NOTE**: optional or follow-up (simplification, placement, a missing safeguard with no bug today).

## Rules for every reviewer

- Read-only. Do not edit, write, or create files, and run nothing that changes the repo or git state
  (no checkout, merge, commit, stash, reset). A branch you are given by ref is read with
  `git diff origin/<base>...<head>` and `git show <head>:<path>`, never checked out.
- Inputs: the diff, the changed files in full (not only the hunks) and the callers and callees you
  need, `AGENTS.md`, and the conventions under `docs/` that `AGENTS.md` names. Tests are part of the
  diff.
- You have not seen the author's reasoning. Do not assume the change is correct. Do not read `plan/`,
  `local/`, commit messages, or any PR description.
- Report each finding exactly as: `SEVERITY | path:line | the issue | the concrete scenario that
  breaks it`. Line numbers refer to the file at the head.
- No finding without a file, a line, and a concrete failing scenario. Report a defect once, per root
  cause. At most 8 findings, most severe first. If you find nothing, say so and list what you checked.
- Suggest a fix only as a one-line pointer. Never implement one.
- End with `Files read: <n>` and `Self-assessed confidence: <low|medium|high>`.

## Architecture and conventions

Apply the repo's rules to the diff: `docs/architecture/architecture-conventions.md` and the style
guides `docs/conventions/general-style.md`, `python-style.md`, and `frontend-style.md`. The gate has
checked imports and formatting; this review judges what scripts cannot.
- Layering and ownership despite legal imports: logic in the wrong layer, dependency direction.
- Placement: side-effect-free decision logic belongs in `domain/`, not next to a repository read.
- One rule split across two modules; a definition far from its only user.
- Safety conventions: the Live Trading Safety Guard, the three broker guard errors never caught.
- Style rules ruff cannot enforce: timestamps written to the database use the helpers in
  `src/common/time.py`; comments and docstrings state facts, not the author's reasoning or the
  change's history (more prose lines than code lines is the usual tell).
- Docs that now describe the code wrongly (maps, reference notes) when the diff changes what they
  describe.

## Break it

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

## Operator

Judge the change by the person who has to find out it broke, at 3 a.m.
- When this fails, what is the first thing the operator sees? Does the log name the cause?
- Does an alert fire? Which one, to whom? What fails silently (host off, no transport configured)?
- Does the runbook say what to do? Is a doc now stale or wrong?
- Does it add a recurring manual step, and is that step documented and checkable?
- Docs: diff the changed behavior against every runbook and reference doc that describes it,
  including files the PR did not touch. Check that a documented command or grep still finds what the
  runbook says it finds.

## Test skeptic

Judge whether the tests would catch a regression. You cannot check the branch out or run tests;
reason from the test and the code.
- Would each new test fail if the change were reverted? Walk through it.
- What behavior in the diff has no test? List the paths.
- Do tests assert behavior or only that code ran? Are mocks hiding the real integration?
- Is a test copying the implementation's logic instead of stating the expected result?
- For each behavior gap, say whether it hides a bug (a wrong result today) or only a missing
  safeguard, and name the missing test.

## Simplifier

Find what can be deleted or made plainer. This repo prefers minimal tooling. It is selected for
diffs of 200 or more changed lines outside documentation, and for any diff that adds a source module.
- Code, parameters, flags, or helpers added that nothing needs yet.
- Two ways to do one thing; a new abstraction with one user.
- Defensive code for situations that cannot occur.
- Comments or docstrings that narrate reasoning or history instead of stating facts
  (`docs/conventions/python-style.md`, Comments and docstrings).

## For the orchestrator

Used by `pr ready` and by a review of a PR by number.
1. **Pick the reviewers.** Run `review_scope_check`; it prints them. Security-class concerns
   (credentials, authorization, network exposure) go to `/security-review`, not to a lens.
2. **Spawn.** One read-only agent per reviewer, in parallel (the `Plan` agent type has no edit
   tools), Sonnet for all of them; the second Break it sample runs on Opus. Give each a one-line
   prompt naming this file, its section, and the base and head refs. Do not give a reviewer the PR
   description, commit messages, a list of known issues, or the author's report. For a longer prompt
   write it to a file and point the agent at it.
3. **Verify every finding.** Open the file and line and run or reason through the scenario. Drop
   NOT REAL findings. Merge duplicates by root cause.
4. **Assign severity.** The highest any reviewer gave, unless verification lowers it. Record a lowered
   severity on the finding's *Caught by* line with the original and the reason (the format is in
   `check-pr-readiness/SKILL.md`). One defect can be rated differently by different reviewers.
5. **Add a *Tests* line to each defect.** Whether the current tests catch it and the test to add,
   from the Test skeptic's output and your own reading.
6. **Cost.** A reviewer costs about 60-90k tokens whatever the model. Run only the selected ones. On a
   later pass the orchestrator re-verifies open findings by hand and runs reviewers only on a large
   incremental diff (the rule is in `check-pr-readiness/SKILL.md`, Step 4).
7. **Never fix during review.** Findings go to the owner.

## Why these choices

From a pilot on two open PRs (an order-reconciliation change and a skip-unavailable-accounts change),
41 reports, every finding checked against the code. The full record is the plan file
`review-mindsets.md`, deleted when this shipped; it is in git history at the merge commit of PR #295.
- The reviewers found 12 distinct defects that the author's own review missed, including 3 BLOCKERs
  on one PR and a duplicate-trading hole on the other. About 69% of reported findings were real
  (excluding trivial ones), and none of the Sonnet or Opus findings checked was wrong.
- A separate Money and safety lens found nothing that Break it did not, so it is a section of Break it.
- Sonnet matched Opus on recall at lower cost. Haiku found 0 or 1 of the 8 key defects, twice stated "no
  findings" with high confidence, raised a false BLOCKER, and used as many tokens as Sonnet through
  more tool calls: do not use it. Every single run missed at least one key defect, so a second Break it
  sample on Opus covers more than a bigger model on the same lens on risky diffs.
- A pre-read bundle of the diff and files cost more tokens and missed defects that need other files.
- The separate AI Quality step found 2 of 3 key defects on one PR and none of 6 on the other; the
  lenses replaced it. The architecture and style review stayed because no lens covers layering.
- Limits: two PRs, one run per cell, one scorer. Treat the thresholds (200 changed lines for the
  Simplifier) and the model choices as starting points to tune.
