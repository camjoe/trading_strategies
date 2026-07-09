import trading.services.auto_trading as auto_trading_service
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_bridge import default_book_id
from trading.services.accounts import create_account, get_account
from trading.services.auto_trading import RotationDeps
from tests.src.trading.services.auto_trading.factories import make_auto_trading_account

# Selection scores come from the strategy evaluation artifact's decision score; the
# champion/challenger model reads it through the shared decision-score builder.
EVAL_FN = "trading.services.books.rotation_metrics.fetch_strategy_evaluation_for_account_row"


def _artifact(score: float, *, trade_count: int = 30) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=True, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=score, overall_confidence=0.3),
    )


def _patch_scores(monkeypatch, scores: dict[str, float]) -> None:
    monkeypatch.setattr(EVAL_FN, lambda _conn, _account, *, strategy_name: _artifact(scores[strategy_name]))


def _enable_rotation(conn, name: str, *, mode: str = "optimal") -> None:
    conn.execute(
        """
        UPDATE accounts
        SET rotation_enabled = 1,
            rotation_interval_days = 7,
            rotation_schedule = ?,
            rotation_active_index = 0,
            rotation_active_strategy = 'trend',
            rotation_last_at = '2026-03-01T00:00:00Z',
            rotation_mode = ?
        WHERE name = ?
        """,
        ('["trend","mean_reversion"]', mode, name),
    )
    conn.commit()


def _latest_decision(conn, *, book_id: int):
    return conn.execute(
        "SELECT rotation_action FROM rotation_decisions WHERE book_id = ? ORDER BY id DESC LIMIT 1",
        (book_id,),
    ).fetchone()


def test_rotate_runtime_account_if_due_updates_state() -> None:
    account_before = make_auto_trading_account(
        id=9,
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=0,
        rotation_last_at="2026-03-01T00:00:00Z",
        rotation_active_strategy="trend",
    )

    class _Conn:
        def __init__(self):
            self.updated = None
            self.committed = False

        def execute(self, _sql, params):
            self.updated = params

        def commit(self):
            self.committed = True

    conn = _Conn()
    account_after = make_auto_trading_account(
        id=9,
        strategy="mean_reversion",
        rotation_enabled=1,
        rotation_interval_days=7,
        rotation_schedule='["trend","mean_reversion"]',
        rotation_active_index=1,
        rotation_last_at="2026-03-17T00:00:00Z",
        rotation_active_strategy="mean_reversion",
    )

    out = auto_trading_service.rotate_runtime_account_if_due(
        conn,
        "acct",
        account_before,
        "2026-03-17T00:00:00Z",
        RotationDeps(
            is_rotation_due_fn=lambda _row: True,
            # Champion/challenger selects mean_reversion; the account state updates to it.
            select_optimal_strategy_fn=lambda *_args, **_kwargs: "mean_reversion",
            update_account_rotation_state_fn=AccountRepository(conn).update_rotation_state,
            get_account_fn=lambda _conn, _name: account_after,
        ),
    )

    assert conn.committed is True
    assert conn.updated is not None
    assert conn.updated[0] == "mean_reversion"
    assert out["strategy"] == "mean_reversion"


def test_rotate_runtime_account_if_due_rotates_to_higher_decision_score(conn, monkeypatch) -> None:
    create_account(conn, "acct_cc", "trend", 10000.0, "SPY")
    _enable_rotation(conn, "acct_cc")
    account = get_account(conn, "acct_cc")
    # The mean_reversion challenger clears the outperformance + score-superiority gates.
    _patch_scores(monkeypatch, {"trend": 1.0, "mean_reversion": 5.0})

    rotated = auto_trading_service.rotate_runtime_account_if_due(
        conn,
        "acct_cc",
        account,
        "2026-03-20T00:00:00Z",
        RotationDeps(
            is_rotation_due_fn=lambda _row: True,
            select_optimal_strategy_fn=lambda inner_conn, inner_account, inner_as_of: (
                auto_trading_service.select_account_rotation_strategy(inner_conn, inner_account, inner_as_of)
            ),
            update_account_rotation_state_fn=AccountRepository(conn).update_rotation_state,
            get_account_fn=get_account,
        ),
    )

    assert rotated["strategy"] == "mean_reversion"
    assert rotated["rotation_active_strategy"] == "mean_reversion"
    decision = _latest_decision(conn, book_id=default_book_id(conn, int(account["id"])))
    assert decision["rotation_action"] == "rotate"


def test_rotate_runtime_account_if_due_noop_when_not_due() -> None:
    account = make_auto_trading_account(
        rotation_enabled=1,
        rotation_interval_days=30,
        rotation_last_at="2026-03-20T00:00:00Z",
    )

    out = auto_trading_service.rotate_runtime_account_if_due(
        conn=object(),
        account_name="acct",
        account=account,
        now_iso="2026-03-21T00:00:00Z",
        deps=RotationDeps(
            is_rotation_due_fn=lambda *_args, **_kwargs: False,
            select_optimal_strategy_fn=lambda *_args, **_kwargs: None,
            update_account_rotation_state_fn=lambda *_args, **_kwargs: None,
            get_account_fn=get_account,
        ),
    )

    assert out is account


def test_select_account_rotation_strategy_holds_and_records_incumbent(conn, monkeypatch) -> None:
    create_account(conn, "acct_hold", "trend", 10000.0, "SPY")
    _enable_rotation(conn, "acct_hold")
    account = get_account(conn, "acct_hold")
    # Incumbent scores best -> no challenger outperforms -> hold.
    _patch_scores(monkeypatch, {"trend": 5.0, "mean_reversion": 1.0})

    selected = auto_trading_service.select_account_rotation_strategy(conn, account, "2026-03-21T00:00:00Z")

    assert selected == "trend"
    decision = _latest_decision(conn, book_id=default_book_id(conn, int(account["id"])))
    assert decision["rotation_action"] == "hold"


def test_select_account_rotation_strategy_returns_none_when_no_active_strategy() -> None:
    account = make_auto_trading_account(
        id=123,
        strategy="",
        rotation_active_strategy=None,
        rotation_schedule=None,
    )

    # No incumbent to evaluate -> None, and no default-book resolution is attempted.
    assert auto_trading_service.select_account_rotation_strategy(object(), account, "2026-03-21T00:00:00Z") is None
