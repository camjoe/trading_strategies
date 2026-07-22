from __future__ import annotations

from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.services.accounts import get_account
from trading.services.books.rotation.metrics import build_rotation_strategy_metrics
from tests.support.repositories import insert_repository_account

_FETCH_TARGET = "trading.services.evaluation.fetch_strategy_evaluation_for_account_row"


def _artifact(*, blended_score: float | None, trade_count: int, available: bool = True) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=available, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=blended_score, overall_confidence=0.3),
    )


def test_build_rotation_strategy_metrics_maps_decision_score(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_metrics_eval")
    assert account_id is not None
    account = get_account(conn, "acct_metrics_eval")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=4.5, trade_count=18),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="meanrev",
    )

    assert metrics.strategy_name == "meanrev"
    assert metrics.trade_count == 18
    assert metrics.risk_adjusted_return == 4.5
    assert metrics.stability == 0.0
    assert metrics.drawdown_penalty == 0.0


def test_build_rotation_strategy_metrics_defaults_missing_score(conn, monkeypatch) -> None:
    insert_repository_account(conn, name="acct_metrics_missing")
    account = get_account(conn, "acct_metrics_missing")
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=None, trade_count=0, available=False),
    )

    metrics = build_rotation_strategy_metrics(
        conn,
        account=account,
        strategy_name="meanrev",
    )

    assert metrics.risk_adjusted_return == 0.0
    assert metrics.trade_count == 0
