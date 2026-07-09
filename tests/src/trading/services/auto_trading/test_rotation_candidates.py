from __future__ import annotations

from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.services.accounts import get_account
from trading.services.auto_trading.rotation_candidates import build_book_rotation_candidates
from tests.support.repositories import insert_repository_account

EVAL_FN = "trading.services.books.rotation_metrics.fetch_strategy_evaluation_for_account_row"


def _artifact(score: float, *, trade_count: int = 30) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=True, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=score, overall_confidence=0.3),
    )


def _patch_scores(monkeypatch, scores: dict[str, float]) -> None:
    monkeypatch.setattr(EVAL_FN, lambda _conn, _account, *, strategy_name: _artifact(scores[strategy_name]))


def test_build_book_rotation_candidates_enumerates_incumbent_and_challengers(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="rot_acct")
    account = get_account(conn, "rot_acct")
    _patch_scores(monkeypatch, {"trend": 1.0, "meanrev": 5.0, "breakout": 2.0})

    result = build_book_rotation_candidates(
        conn,
        book_id=7,
        account=account,
        incumbent_strategy="trend",
        incumbent_param_set_id=None,
        schedule=["trend", "meanrev", "breakout"],
    )

    assert result.book_id == 7
    assert result.incumbent_strategy == "trend"
    assert result.incumbent.strategy_name == "trend"
    # Challengers are the schedule minus the incumbent, in order.
    assert [c.strategy_name for c in result.challengers] == ["meanrev", "breakout"]
    # A stronger challenger's decision score exceeds the incumbent's (5.0 > 1.0).
    assert result.challengers[0].risk_adjusted_return > result.incumbent.risk_adjusted_return


def test_build_book_rotation_candidates_excludes_incumbent_from_challengers(conn, monkeypatch) -> None:
    # A sleeve book: the incumbent is the book's own assigned strategy, not the account default.
    insert_repository_account(conn, name="rot_acct2")
    account = get_account(conn, "rot_acct2")
    _patch_scores(monkeypatch, {"trend": 1.0, "meanrev": 5.0})

    result = build_book_rotation_candidates(
        conn,
        book_id=11,
        account=account,
        incumbent_strategy="meanrev",
        incumbent_param_set_id=None,
        schedule=["trend", "meanrev"],
    )

    assert result.incumbent_strategy == "meanrev"
    assert [c.strategy_name for c in result.challengers] == ["trend"]


def test_build_book_rotation_candidates_empty_schedule_has_no_challengers(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="rot_acct3")
    account = get_account(conn, "rot_acct3")
    _patch_scores(monkeypatch, {"trend": 1.0})

    result = build_book_rotation_candidates(
        conn,
        book_id=3,
        account=account,
        incumbent_strategy="trend",
        incumbent_param_set_id=None,
        schedule=[],
    )

    assert result.incumbent.strategy_name == "trend"
    assert result.challengers == []
