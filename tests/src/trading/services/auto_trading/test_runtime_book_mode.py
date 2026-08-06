from __future__ import annotations

import json
from unittest.mock import Mock

import trading.services.auto_trading.runtime as runtime_service
from tests.src.trading.services.auto_trading.factories import FakeBroker, make_feature_fetchers
from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.models.evaluation import EvaluationBacktestEvidence, EvaluationConfidence, StrategyEvaluationArtifact
from trading.models.execution import BookTradeCandidate
from trading.models.orders import OrderFill, OrderStatus
from trading.repositories.books import BookRepository
from trading.repositories.ledger import LedgerRepository
from trading.repositories.orders import OrderRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.auto_trading.runtime import run_for_account
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.operational_settings import set_runtime_throttle_settings

DEFAULT_RUNTIME_NOW_ISO = "2026-05-03T14:00:00Z"


def _patch_rotation_evaluation(monkeypatch, scores: dict[str, float], *, trade_count: int = 30) -> None:
    """Drive book rotation scoring via stubbed evaluation artifacts per strategy."""

    def _fake_fetch(_conn, _account, *, strategy_name):
        return StrategyEvaluationArtifact(
            backtest=EvaluationBacktestEvidence(available=True, trade_count=trade_count),
            confidence=EvaluationConfidence(
                blended_score=scores.get(strategy_name, 0.0),
                overall_confidence=0.3,
            ),
        )

    monkeypatch.setattr(
        "trading.services.evaluation.fetch_strategy_evaluation_for_account_row",
        _fake_fetch,
    )


def _make_buy_intent(*, account_id: int, book_id: int, qty: int = 1) -> BookTradeCandidate:
    return BookTradeCandidate(
        account_id=account_id,
        book_id=book_id,
        strategy_name="trend",
        side="buy",
        symbol="AAPL",
        qty=qty,
        requested_price=100.0,
        forced_sell=None,
        delta_est=None,
        iv_est=None,
    )


def _patch_single_buy_intent(
    monkeypatch,
    conn,
    *,
    account_id: int,
    book_id: int,
    qty: int = 1,
) -> None:
    del conn  # kept for call-site compatibility
    monkeypatch.setattr(
        runtime_service,
        "generate_book_trade_intents",
        lambda *_args, **_kwargs: [_make_buy_intent(account_id=account_id, book_id=book_id, qty=qty)],
    )


def _patch_runtime_book_execution(
    monkeypatch,
    *,
    now_iso: str = DEFAULT_RUNTIME_NOW_ISO,
) -> None:
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: now_iso)


def _patch_reconciliation_clean(monkeypatch) -> None:
    """Bypass the pre-flight equity reconciliation (tested separately) so submission/gate
    behaviour is isolated from the fixture's default-book equity."""
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_args, **_kwargs: [])


def _patch_reconciliation_reasons(monkeypatch, reasons: list[str]) -> None:
    monkeypatch.setattr(runtime_service, "reconcile_book_equity", lambda *_args, **_kwargs: list(reasons))


# ---------------------------------------------------------------------------


def test_run_for_account_book_mode_applies_rotation_before_intent_generation(
    rotation_book_env, conn, monkeypatch
) -> None:
    account_name = rotation_book_env.account_name
    book_id = rotation_book_env.book_id

    _patch_runtime_book_execution(monkeypatch, now_iso="2026-05-05T14:00:00Z")
    _patch_rotation_evaluation(monkeypatch, {"trend": 0.0, "meanrev": 5.0})
    captured = {"active_strategy": None}

    def _capture_intents(*_args, **_kwargs):
        assignment = open_assignment_for_book(conn, book_id=book_id)
        captured["active_strategy"] = assignment.strategy_name.strip() if assignment is not None else None
        return []

    monkeypatch.setattr(runtime_service, "generate_book_trade_intents", _capture_intents)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=Mock(),
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    assert captured["active_strategy"] == "meanrev"
    latest_decision = RotationDecisionRepository(conn).fetch_latest_for_book(book_id=book_id)
    assert latest_decision is not None
    assert latest_decision.rotation_action == "rotate"
    assert latest_decision.selected_strategy == "meanrev"


def test_run_for_account_book_mode_respects_rotation_cooldown(rotation_book_env, conn, monkeypatch) -> None:
    account_name = rotation_book_env.account_name
    book_id = rotation_book_env.book_id
    RotationDecisionRepository(conn).insert_for_book(
        book_id=book_id,
        decision_time="2026-05-05T10:00:00Z",
        incumbent_strategy="trend",
        challenger_strategy="meanrev",
        selected_strategy="meanrev",
        rotation_action="rotate",
        cooldown_active=0,
        score_components_json="{}",
        gate_results_json="{}",
        decision_reason="rotate_to_challenger",
        config_version="cfg-old",
        created_at="2026-05-05T10:00:00Z",
    )

    _patch_runtime_book_execution(monkeypatch, now_iso="2026-05-05T14:00:00Z")
    _patch_rotation_evaluation(monkeypatch, {"trend": 0.0, "meanrev": 5.0})
    captured = {"active_strategy": None}

    def _capture_intents(*_args, **_kwargs):
        assignment = open_assignment_for_book(conn, book_id=book_id)
        captured["active_strategy"] = assignment.strategy_name.strip() if assignment is not None else None
        return []

    monkeypatch.setattr(runtime_service, "generate_book_trade_intents", _capture_intents)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=Mock(),
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    assert captured["active_strategy"] == "trend"
    latest_decision = RotationDecisionRepository(conn).fetch_latest_for_book(book_id=book_id)
    assert latest_decision is not None
    assert latest_decision.rotation_action == "hold"
    assert latest_decision.decision_reason == "cooldown_active"
    assert latest_decision.cooldown_active == 1


def test_run_for_account_book_mode_submits_and_persists_orders(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id
    broker = FakeBroker()

    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 1
    # The book submits through the shared service onto its bridging book's clean tables.
    orders = OrderRepository(conn).fetch_for_book(book_id=book_id)
    assert len(orders) == 1
    order = orders[0]
    assert order.symbol == "AAPL"
    assert order.side == "buy"
    assert float(order.qty) == 1.0
    assert order.status == "filled"
    assert order.broker_order_id == "fake-broker-order"

    assert PositionRepository(conn).fetch(book_id=book_id, symbol="AAPL") is not None
    assert LedgerRepository(conn).fetch_for_book(book_id=book_id) != []

    fill_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM order_fills f
        JOIN orders o ON o.id = f.order_id
        WHERE o.account_id = ?
        """,
        (account_id,),
    ).fetchone()
    assert fill_count is not None
    assert int(fill_count["n"]) == 1

    # Book balances (not the frozen book balances) reflect the fill: 1000 - 100 = 900 cash.
    book = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert book is not None
    assert book.current_cash == 900.0
    assert book.current_equity == 1_000.0

    risk_snapshot = conn.execute(
        """
        SELECT max_symbol_concentration_pct, max_sector_concentration_pct
        FROM risk_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert risk_snapshot is not None
    assert float(risk_snapshot["max_symbol_concentration_pct"]) > 0
    assert float(risk_snapshot["max_sector_concentration_pct"]) > 0
    decision_rows = conn.execute(
        """
        SELECT action, reason_code
        FROM risk_decisions
        WHERE account_id = ?
        ORDER BY id ASC
        """,
        (account_id,),
    ).fetchall()
    assert len(decision_rows) >= 1
    assert decision_rows[0]["action"] == "allow"

    broker.place_order.assert_called_once()
    broker.disconnect.assert_called_once()


def test_run_for_account_trade_throttle_blocks_submission(book_env, conn, monkeypatch) -> None:
    # The global trade throttle (operational settings) gates the book path:
    # a hit day cap blocks submission and records a risk decision.
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id
    broker = FakeBroker()

    set_runtime_throttle_settings(
        conn,
        runtime_max_trades_per_day=1,
        runtime_max_trades_per_minute=None,
        updated_at=DEFAULT_RUNTIME_NOW_ISO,
    )
    from tests.support.fills import seed_fill_event

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        trade_time=DEFAULT_RUNTIME_NOW_ISO,
    )

    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker.place_order.assert_not_called()
    broker.disconnect.assert_called_once()
    throttle_rows = conn.execute(
        "SELECT reason_code FROM risk_decisions WHERE account_id = ? AND action = 'block'",
        (account_id,),
    ).fetchall()
    assert any(row["reason_code"] == "trade_throttle_exceeded" for row in throttle_rows)


def test_run_for_account_book_mode_applies_risk_rescale_before_submit(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id
    broker = FakeBroker()

    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id, qty=5)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 1
    broker.place_order.assert_called_once()
    broker_order = broker.place_order.call_args.args[0]
    assert broker_order.qty == 2.0

    # The notional cap rescaled the intent from 5 to 2 shares before submission.
    orders = OrderRepository(conn).fetch_for_book(book_id=book_id)
    assert len(orders) == 1
    assert float(orders[0].qty) == 2.0
    rescale_row = conn.execute(
        """
        SELECT action, reason_code, requested_qty, approved_qty
        FROM risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert rescale_row is not None
    assert rescale_row["action"] == "rescale"
    assert rescale_row["reason_code"] == "book_notional_cap"
    assert int(rescale_row["requested_qty"]) == 5
    assert int(rescale_row["approved_qty"]) == 2


def test_run_for_account_book_mode_kill_switch_stale_price_blocks_submission(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id

    broker = FakeBroker()
    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 0.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "stale_price_data" in payload["kill_switch_reasons"]
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert decision_row is not None
    assert decision_row["action"] == "block"
    assert decision_row["reason_code"] == "stale_price_data"


def test_run_for_account_book_mode_kill_switch_reconciliation_mismatch(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id
    broker = FakeBroker()

    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_reasons(monkeypatch, ["reconciliation_mismatch"])
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "reconciliation_mismatch" in payload["kill_switch_reasons"]
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert decision_row is not None
    assert decision_row["action"] == "block"
    assert decision_row["reason_code"] == "reconciliation_mismatch"


def test_run_for_account_book_mode_kill_switch_broker_anomaly(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id

    class _FailingBroker:
        def __init__(self) -> None:
            self.disconnect_calls = 0

        def place_order(self, _order):
            raise RuntimeError("ib anomaly")

        def disconnect(self) -> None:
            self.disconnect_calls += 1

    broker = _FailingBroker()
    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "broker_api_anomaly" in payload["kill_switch_reasons"]
    # The broker raised before any order was persisted → no clean order row.
    assert OrderRepository(conn).fetch_for_book(book_id=book_id) == []
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert decision_row is not None
    assert decision_row["action"] == "block"
    assert decision_row["reason_code"] == "broker_api_anomaly"
    assert broker.disconnect_calls == 1


def test_run_for_account_book_mode_kill_switch_stale_reconciliation_snapshot(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_book")
    book_id = insert_test_book(
        conn,
        account_id=account_id,
        start_equity=1_000.0,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time="2026-05-01T00:00:00Z",
        cash=1_000.0,
        market_value=0.0,
        equity=1_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )

    broker = FakeBroker()
    _patch_runtime_book_execution(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name="acct_book",
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "stale_reconciliation_snapshot" in payload["kill_switch_reasons"]


def test_run_for_account_book_mode_kill_switch_when_reconciliation_snapshot_missing_value_error(
    book_env, conn, monkeypatch
) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id

    broker = FakeBroker()
    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_reasons(monkeypatch, ["reconciliation_snapshot_missing"])
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "reconciliation_snapshot_missing" in payload["kill_switch_reasons"]


def test_run_for_account_book_mode_submitted_order_with_no_broker_id_skips_broker_rows(
    book_env, conn, monkeypatch
) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id

    class _NoBrokerIdBroker:
        def place_order(self, order):
            order.broker_order_id = None
            order.status = OrderStatus.SUBMITTED
            order.filled_qty = 0.0
            order.avg_fill_price = None
            order.fills = []
            return order

        def disconnect(self) -> None:
            return None

    broker = _NoBrokerIdBroker()
    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 1
    # The clean order carries a null broker id (the legacy broker_orders table is gone).
    orders = OrderRepository(conn).fetch_for_book(book_id=book_id)
    assert len(orders) == 1
    assert orders[0].status == "submitted"
    assert orders[0].broker_order_id is None


def test_run_for_account_book_mode_persists_broker_fills_when_present(book_env, conn, monkeypatch) -> None:
    account_name = book_env.account_name
    account_id = book_env.account_id
    book_id = book_env.book_id

    class _BrokerWithFill:
        def place_order(self, order):
            order.broker_order_id = "fill-broker-order"
            order.status = OrderStatus.SUBMITTED
            order.filled_qty = 0.0
            order.avg_fill_price = None
            order.fills = [
                OrderFill(
                    filled_qty=1.0,
                    fill_price=100.5,
                    fill_time="2026-05-03T14:00:05Z",
                    commission=0.0,
                    exec_id="fill-001",
                )
            ]
            return order

        def disconnect(self) -> None:
            return None

    broker = _BrokerWithFill()
    _patch_runtime_book_execution(monkeypatch)
    _patch_reconciliation_clean(monkeypatch)
    _patch_single_buy_intent(monkeypatch, conn, account_id=account_id, book_id=book_id)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=lambda _, b=broker: b,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 1
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM order_fills f
        JOIN orders o ON o.id = f.order_id
        WHERE o.broker_order_id = ?
        """,
        ("fill-broker-order",),
    ).fetchone()
    assert row is not None
    assert int(row["n"]) == 1
