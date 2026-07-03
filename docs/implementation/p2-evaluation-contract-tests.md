# Implementation Guide — P2 / 1c: Evaluation decision-score contract regression tests

Type: implementation
Status: Ready
Purpose: Work order for P2/1c — cross-surface regression tests proving compare, promotion, and rotation read one decision-score contract; doubles as the work-order template.
Initiative: P2 (Unify evaluation) — sub-feature 1c
Estimate: S (test-only, ~half day)
Created: 2026-07-01
Last Reviewed: 2026-07-02
Related: [Plan](../plan.md), [Decisions](../decisions.md), [Overview](../overview.md)

> **This file is both the 1c work order and the template** for per-initiative implementation guides.
> An agent should be able to execute it start-to-finish without further questions. When creating the
> next guide, copy this section structure. Sections marked _(template)_ generalize to every guide.
>
> **Light-model handoff:** follow the execution protocol in [README.md](README.md) — make only the
> specified changes, run the checks, commit if green, and **stop and report** on anything ambiguous
> or red. Do not design, weaken a test, or expand scope.

---

## 1. Objective

Add a cross-surface regression test proving that **compare, promotion, and rotation all read the same
decision-score contract** (`EvaluationDecisionScore` via `derive_decision_score`) and **handle missing
evidence identically**. This closes sub-feature 1c and completes initiative P2. It is **test-only** —
no production behavior changes.

### Definition of Done
- [ ] One test module asserts the three surfaces derive score/confidence/data-gaps from the same
      contract for the same artifact.
- [ ] Four evidence scenarios are covered: complete, missing-backtest, missing-paper/live, null score.
- [ ] `python -m scripts.run_checks --profile quick` is green (layer + ruff + mypy + targeted tests).
- [ ] Committed with the message format in §7; branch pushed (PR optional per §9).
- [ ] Plan P2 status updated (1c ☐ → ✅).

## 2. Preconditions
- 1a and 1b are already merged/present: `src/trading/models/evaluation/evaluation_decision_score.py`,
  `src/trading/domain/evaluation_decision_score.py` (`derive_decision_score`), and
  `src/trading/services/sleeves/shadow_evaluation.py` (`build_sleeve_metrics_from_evaluation`) exist.
- `./.venv` exists. If missing, **stop and ask** (per `AGENTS.md`).

## 3. Background / context

The one contract: `EvaluationDecisionScore { score, confidence, backtest_confidence,
paper_live_confidence, has_evidence, data_gaps }`, produced by
`derive_decision_score(artifact: StrategyEvaluationArtifact)`.

The three consumers to pin:
1. **Compare / promotion payload** — `apps/paper_trading_web/backend/services/evaluation.py`
   `build_evaluation_summary_payload(artifact)` returns `blendedScore`, `overallConfidence`,
   `backtestConfidence`, `paperLiveConfidence`, `dataGaps` (already sourced via `derive_decision_score`).
2. **Promotion policy** — `src/trading/domain/promotion_policy.py` `assess_promotion_readiness(artifact)`
   gates on `artifact.confidence.overall_confidence` and `artifact.diagnostics.data_gaps`.
3. **Rotation** — `src/trading/services/sleeves/shadow_evaluation.py`
   `build_sleeve_metrics_from_evaluation(...)` sets `risk_adjusted_return = decision.score or 0.0`.

Existing patterns to reuse: `tests/src/trading/domain/test_evaluation_decision_score.py` (artifact
construction + the four scenarios) and `tests/support/evaluation.py`.

## 4. Guardrails _(template)_
- Use the venv interpreter: `.venv\Scripts\python.exe` (Windows) / `./.venv/bin/python` (POSIX). Never system Python.
- Respect layering (`docs/architecture/architecture-conventions.md`); this task adds tests only.
- **Test-only. Do not change production code.** If the test reveals a real inconsistency (a genuine
  bug), **stop and report it** — do not "fix" it by altering the contract, since that is a behavior
  change needing review.
- Never set `live_trading_enabled`; never touch broker endpoints.

## 5. Branch & commit strategy _(template)_
- **Branch:** create/verify a dedicated branch off the integration base, e.g.
  `git switch -c features/p2-1c-eval-contract-tests` (from `main` or the current integration branch).
  _For this example specifically, continuing on the existing `features/evaluation-phase-2` branch is
  also acceptable._
- **Commit points:** this is small — **one commit** after §8 validation is green. (Larger initiatives:
  commit at each logically complete, green sub-step.)
- **Commit message format:**
  ```
  <concise summary of what changed>

  <1-3 line body: why / scope>

  Co-Authored-By: <model name> <noreply@anthropic.com>
  ```
  (Use the **executing model's own** name in the `Co-Authored-By` line.)
- Do **not** commit if any check in §8 fails. Commit only after green.

## 6. Implementation steps

1. **Create** `tests/apps/paper_trading_web/backend/services/test_decision_contract_consistency.py`.
   Import the compare payload builder as `from paper_trading_web.backend.services.evaluation import
   build_evaluation_summary_payload` (the apps backend is importable as `paper_trading_web...`, **not**
   `apps.paper_trading_web...`); all `trading...` imports resolve normally.
2. Add an `_artifact(*, blended_score, backtest_confidence, paper_live_confidence, overall_confidence,
   backtest_trade_count, data_gaps)` helper building a `StrategyEvaluationArtifact` from
   `EvaluationConfidence`, `EvaluationBacktestEvidence`, and `EvaluationDiagnostics` (mirror the
   existing adapter test).
3. For each of the four scenarios (complete / missing-backtest / missing-paper-live / null score),
   compute `decision = derive_decision_score(artifact)` and assert **all three surfaces agree**:
   - **Compare/promotion payload:** `p = build_evaluation_summary_payload(artifact)` →
     `p["blendedScore"] == decision.score`, `p["overallConfidence"] == decision.confidence`,
     `p["backtestConfidence"] == decision.backtest_confidence`,
     `p["paperLiveConfidence"] == decision.paper_live_confidence`,
     `p["dataGaps"] == list(decision.data_gaps)`.
   - **Promotion policy:** `a = assess_promotion_readiness(artifact)` →
     `a.overall_confidence == decision.confidence` and `list(a.data_gaps) == list(decision.data_gaps)`.
   - **Rotation:** monkeypatch
     `trading.services.sleeves.shadow_evaluation.fetch_strategy_evaluation_for_account_row` to return
     the artifact, call `build_sleeve_metrics_from_evaluation(conn, account=..., strategy_name=...,
     param_set_id=None)`, and assert
     `metrics.risk_adjusted_return == (decision.score if decision.score is not None else 0.0)` and
     `metrics.trade_count == (artifact.backtest.trade_count or 0)`.
     `conn` and `account` are only forwarded to the monkeypatched fetch, so pass placeholders
     (`object()`) — **no DB fixture is needed**.
4. All scenario inputs are whole numbers, so assert exact equality with `==` (do **not** use
   `pytest.approx`).

## 7. Validation _(template — commands are exact)_

Run from repo root with the venv interpreter:

```
.venv\Scripts\python.exe -m scripts.checks.run_suite apps/paper_trading_web --no-cov
.venv\Scripts\python.exe -m scripts.checks.layer_check
.venv\Scripts\python.exe -m scripts.checks.mypy_check
.venv\Scripts\python.exe -m scripts.run_checks --profile quick
```

Expected: the new test passes; layer check clean; mypy clean; quick profile green. If `run_checks
--profile quick` already runs the suite + lint + types, it is the single gate — the individual
commands above are for fast iteration.

## 8. Failure handling _(template)_
- Test fails because a surface genuinely diverges from the contract → **stop, report** the divergence
  (surface, scenario, expected vs actual). Do not change production code to force green.
- mypy/layer failure in the new test → fix the test.
- Any check red → do not commit; fix or report.

## 9. Handoff / PR _(template)_
- After a green commit, push the branch.
- Open a PR to the integration base with `gh pr create` summarizing scope + validation, **or** hand
  back to the operator if they prefer to merge — default: open the PR and report the URL.
- Update [plan.md](../plan.md): P2 row status 1c ☐ → ✅ (and the 1c "Done when" checkbox).

## 10. Out of scope
- Any change to `derive_decision_score`, payload builders, promotion policy, or rotation logic.
- Rotation's account-episode path (that is P4/2b).

## 11. Final report _(template — per `AGENTS.md` output style)_
- **Developer verification:** name the test module + the surfaces asserted.
- **Validation run:** the §7 commands and their results.
- **Cleanup/robustness notes:** obsolete code removed or `none found in touched scope`.
