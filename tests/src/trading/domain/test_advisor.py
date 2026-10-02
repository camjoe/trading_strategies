from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from trading.domain.advisor import (
    build_review_flags,
    counterfactual_verdict,
    due_for_scoring,
    outcome_window_end,
    plan_counterfactual,
)
from trading.models.advisor import (
    FLAG_BACKTEST_STALE,
    FLAG_DATA_GAPS,
    FLAG_DECISIONS_DUE,
    FLAG_NO_PAPER_EVIDENCE,
    FLAG_NO_WALK_FORWARD,
    FLAG_PAPER_RETURN_NEGATIVE,
    StrategyDecisionOutcome,
    StrategyDecisionRecord,
)
from trading.models.evaluation import (
    BacktestFreshness,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)


def _record(*, decision_id: int = 1, created_at: str, window_days: int = 21) -> StrategyDecisionRecord:
    return StrategyDecisionRecord(
        id=decision_id,
        account_id=1,
        decision_type="hold",
        rationale="r",
        evidence_json="{}",
        decided_by="agent",
        created_at=created_at,
        outcome_window_days=window_days,
        outcome=StrategyDecisionOutcome(outcome_status="pending"),
    )


def _healthy_evaluation() -> StrategyEvaluationArtifact:
    artifact = StrategyEvaluationArtifact()
    return replace(
        artifact,
        walk_forward=EvaluationWalkForwardEvidence(available=True),
        paper_live=EvaluationPaperLiveEvidence(available=True, return_pct=1.2),
        diagnostics=EvaluationDiagnostics(
            backtest_freshness=BacktestFreshness(available=True, age_days=3.0, stale_threshold_days=30)
        ),
    )


def _codes(evaluation: StrategyEvaluationArtifact, *, due_count: int = 0) -> list[str]:
    return [flag.code for flag in build_review_flags(evaluation, due_count=due_count)]


def test_window_end_counts_trading_days_from_the_decision_date() -> None:
    # Thursday 2026-10-01 + 2 trading days = Monday 2026-10-05.
    assert outcome_window_end(_record(created_at="2026-10-01T15:00:00Z", window_days=2)) == date(2026, 10, 5)


def test_due_for_scoring_keeps_only_closed_windows() -> None:
    closed = _record(decision_id=1, created_at="2026-09-01T00:00:00Z", window_days=5)
    open_ = _record(decision_id=2, created_at="2026-09-30T00:00:00Z", window_days=5)

    due = due_for_scoring([closed, open_], as_of=date(2026, 10, 2))

    assert [record.id for record in due] == [1]


def test_a_window_closing_today_is_due() -> None:
    record = _record(created_at="2026-10-01T00:00:00Z", window_days=1)
    assert due_for_scoring([record], as_of=date(2026, 10, 2)) == [record]


def test_healthy_evaluation_raises_no_flags() -> None:
    assert _codes(_healthy_evaluation()) == []


def test_empty_evaluation_flags_the_missing_evidence() -> None:
    assert _codes(StrategyEvaluationArtifact()) == [FLAG_NO_WALK_FORWARD, FLAG_NO_PAPER_EVIDENCE]


def test_due_decisions_are_flagged_first() -> None:
    assert _codes(_healthy_evaluation(), due_count=2) == [FLAG_DECISIONS_DUE]


def test_stale_backtest_negative_paper_and_gaps_are_flagged() -> None:
    evaluation = replace(
        _healthy_evaluation(),
        paper_live=EvaluationPaperLiveEvidence(available=True, return_pct=-3.4),
        diagnostics=EvaluationDiagnostics(
            data_gaps=["missing benchmark"],
            backtest_freshness=BacktestFreshness(
                available=True, age_days=45.0, stale_threshold_days=30, is_stale=True
            ),
        ),
    )
    flags = build_review_flags(evaluation, due_count=0)

    assert [flag.code for flag in flags] == [FLAG_BACKTEST_STALE, FLAG_PAPER_RETURN_NEGATIVE, FLAG_DATA_GAPS]
    assert "45 days old" in flags[0].reason
    assert "not benchmark-relative" in flags[1].reason


def test_data_gaps_flag_omits_gaps_that_have_their_own_flag() -> None:
    evaluation = replace(
        StrategyEvaluationArtifact(),
        diagnostics=EvaluationDiagnostics(
            data_gaps=["missing_backtest_evidence", "missing_paper_live_evidence", "missing_walk_forward_evidence"]
        ),
    )
    flags = build_review_flags(evaluation, due_count=0)

    assert [flag.code for flag in flags] == [FLAG_NO_WALK_FORWARD, FLAG_NO_PAPER_EVIDENCE, FLAG_DATA_GAPS]
    assert flags[-1].reason == "missing_backtest_evidence"


@pytest.mark.parametrize(
    ("chosen", "alternative", "verdict"),
    [
        (5.0, 3.0, "helped"),
        (3.0, 5.0, "hurt"),
        (3.5, 3.0, "neutral"),
        (3.0, 3.5, "neutral"),
        (4.0, 3.0, "neutral"),  # exactly the band edge stays neutral
    ],
)
def test_counterfactual_verdict_uses_a_neutral_band(chosen: float, alternative: float, verdict: str) -> None:
    assert counterfactual_verdict(chosen_return_pct=chosen, alternative_return_pct=alternative) == verdict


def _scored_record(*, decision_type: str, strategy_id: int | None, alternative_strategy_id: int | None):
    return replace(
        _record(created_at="2026-10-01T00:00:00Z"),
        decision_type=decision_type,
        strategy_id=strategy_id,
        alternative_strategy_id=alternative_strategy_id,
    )


def test_plan_compares_the_chosen_strategy_with_the_rejected_one() -> None:
    plan = plan_counterfactual(_scored_record(decision_type="hold", strategy_id=1, alternative_strategy_id=2))
    assert (plan.chosen_strategy_id, plan.alternative_strategy_id, plan.unscorable_reason) == (1, 2, None)


def test_plan_for_a_disabled_strategy_compares_cash_with_that_strategy() -> None:
    plan = plan_counterfactual(
        _scored_record(decision_type="disable_strategy", strategy_id=4, alternative_strategy_id=None)
    )
    assert (plan.chosen_strategy_id, plan.alternative_strategy_id) == (None, 4)


@pytest.mark.parametrize(
    ("decision_type", "strategy_id", "alternative_strategy_id", "reason"),
    [
        ("run_experiment", 1, None, "run_experiment"),
        ("hold", None, 2, "no strategy"),
        ("adjust_params", 1, None, "no rejected alternative"),
        ("disable_strategy", None, None, "no strategy"),
    ],
)
def test_plan_reports_why_a_decision_is_unscorable(
    decision_type: str, strategy_id: int | None, alternative_strategy_id: int | None, reason: str
) -> None:
    plan = plan_counterfactual(
        _scored_record(
            decision_type=decision_type, strategy_id=strategy_id, alternative_strategy_id=alternative_strategy_id
        )
    )
    assert reason in (plan.unscorable_reason or "")
