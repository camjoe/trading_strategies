from __future__ import annotations

from trading.domain.rotation import dump_rotation_schedule
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.sleeves import SleeveRepository
from trading.services.accounts import get_account
from trading.services.sleeves.shadow_evaluation import build_sleeve_shadow_evaluation
from tests.support.repositories import insert_repository_account

# The per-strategy metrics builder (which reads the evaluation artifact) lives in
# rotation_metrics; patch the fetch where that module looks it up.
_FETCH_TARGET = "trading.services.sleeves.rotation_metrics.fetch_strategy_evaluation_for_account_row"


def _artifact(*, blended_score: float | None, trade_count: int, available: bool = True) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=available, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=blended_score, overall_confidence=0.3),
    )


def test_build_sleeve_shadow_evaluation_builds_incumbent_and_challengers(conn, monkeypatch) -> None:
    account_name = "acct_shadow_eval"
    account_id = insert_repository_account(conn, name=account_name, strategy="trend")
    conn.execute(
        """
        UPDATE accounts
        SET rotation_schedule = ?
        WHERE id = ?
        """,
        (dump_rotation_schedule(["trend", "meanrev", "breakout"]), account_id),
    )
    conn.commit()
    sleeve_repo = SleeveRepository(conn)
    sleeve_id = sleeve_repo.insert(
        account_id=account_id,
        name="core",
        status="active",
        base_ccy="USD",
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    sleeve_repo.insert_assignment(
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    account = get_account(conn, account_name)

    scores = {"trend": 1.0, "meanrev": 2.0, "breakout": 0.5}
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(blended_score=scores[strategy_name], trade_count=5),
    )

    result = build_sleeve_shadow_evaluation(
        conn,
        account=account,
        as_of_iso="2026-05-07T12:00:00Z",
        rolling_window_days=30,
    )

    assert result.account_name == account_name
    assert len(result.sleeves) == 1
    sleeve = result.sleeves[0]
    assert sleeve.sleeve_id == sleeve_id
    assert sleeve.incumbent_strategy == "trend"
    assert sleeve.incumbent.strategy_name == "trend"
    assert sleeve.incumbent.risk_adjusted_return == 1.0
    assert [item.strategy_name for item in sleeve.challengers] == ["meanrev", "breakout"]
    assert [item.risk_adjusted_return for item in sleeve.challengers] == [2.0, 0.5]
    assert all(item.trade_count == 5 for item in sleeve.challengers)
