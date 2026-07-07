from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.book_bridge import default_book_id
from trading.services.accounts import create_account, get_account
from trading.services.auto_trading.book_rotation import evaluate_account_rotation_decision

EVAL_FN = "trading.services.sleeves.shadow_evaluation.fetch_strategy_evaluation_for_account_row"


def _artifact(score: float, *, trade_count: int = 30) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=True, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=score, overall_confidence=0.3),
    )


def _patch_scores(monkeypatch, scores: dict[str, float]) -> None:
    monkeypatch.setattr(EVAL_FN, lambda _conn, _account, *, strategy_name: _artifact(scores[strategy_name]))


def _set_rotation(conn, name: str, *, schedule: str) -> None:
    conn.execute(
        "UPDATE accounts SET rotation_active_strategy = 'trend', rotation_schedule = ? WHERE name = ?",
        (schedule, name),
    )
    conn.commit()


def _fetch_decision(conn, *, book_id: int):
    return conn.execute(
        """
        SELECT d.rotation_action, d.decision_reason, ss.strategy_key AS selected_strategy
        FROM rotation_decisions d
        LEFT JOIN strategies ss ON ss.id = d.selected_strategy_id
        WHERE d.book_id = ?
        ORDER BY d.id DESC LIMIT 1
        """,
        (book_id,),
    ).fetchone()


def test_evaluate_account_rotation_decision_rotates_and_records(conn, monkeypatch) -> None:
    create_account(conn, "acct_a", "trend", 10000.0, "SPY")
    _set_rotation(conn, "acct_a", schedule='["trend","mean_reversion"]')
    account = get_account(conn, "acct_a")
    _patch_scores(monkeypatch, {"trend": 1.0, "mean_reversion": 5.0})

    selected = evaluate_account_rotation_decision(conn, account, "2026-03-20T00:00:00Z")

    assert selected == "mean_reversion"
    decision = _fetch_decision(conn, book_id=default_book_id(conn, int(account["id"])))
    assert decision["rotation_action"] == "rotate"
    assert decision["selected_strategy"] == "mean_reversion"


def test_evaluate_account_rotation_decision_holds_incumbent_when_no_challengers(conn, monkeypatch) -> None:
    create_account(conn, "acct_b", "trend", 10000.0, "SPY")
    _set_rotation(conn, "acct_b", schedule='["trend"]')  # incumbent only, no challengers
    account = get_account(conn, "acct_b")
    _patch_scores(monkeypatch, {"trend": 3.0})

    selected = evaluate_account_rotation_decision(conn, account, "2026-03-20T00:00:00Z")

    assert selected == "trend"
    decision = _fetch_decision(conn, book_id=default_book_id(conn, int(account["id"])))
    assert decision["rotation_action"] == "hold"
    assert decision["decision_reason"] == "no_challenger_candidates"


def test_evaluate_account_rotation_decision_returns_none_without_incumbent() -> None:
    from tests.src.trading.services.auto_trading.factories import make_auto_trading_account

    account = make_auto_trading_account(strategy="", rotation_active_strategy=None, rotation_schedule=None)
    assert evaluate_account_rotation_decision(object(), account, "2026-03-20T00:00:00Z") is None
