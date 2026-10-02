from __future__ import annotations

from dataclasses import replace
from datetime import date

from trading.domain.advisor import build_review_flags, due_for_scoring, outcome_window_end
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
