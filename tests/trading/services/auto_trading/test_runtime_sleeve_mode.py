from __future__ import annotations

import json

from trading.domain.rotation import dump_rotation_schedule
from trading.repositories.snapshots import insert_snapshot_row
from trading.repositories.daily_metrics import upsert_daily_metric
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_strategy_sleeve_by_id,
    insert_sleeve_strategy_assignment,
    insert_strategy_sleeve,
)
from trading.services.accounts import get_account
from trading.services.auto_trading.runtime import run_for_account
import trading.services.auto_trading.runtime as runtime_service
from trading.services.sleeves.execution import SleeveTradeIntent
from trading.services.sleeves.reconciliation import SleeveEquityReconciliationResult
from tests.support.auto_trading import FakeBroker
from tests.support.repositories import insert_repository_account


def _insert_matching_snapshot(conn, *, account_id: int, equity: float) -> None:
    insert_snapshot_row(
        conn,
        account_id=account_id,
        snapshot_time="2026-05-03T13:59:00Z",
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def _insert_rotation_metric_rows(conn, *, account_id: int, sleeve_id: int) -> None:
    upsert_daily_metric(
        conn,
        account_id=account_id,
        sleeve_id=sleeve_id,
        metric_date="2026-05-03",
        return_pct=0.5,
        drawdown_pct=-0.7,
        turnover_pct=2.0,
        slippage_bps=8.0,
        hit_rate=0.45,
        expectancy=0.08,
        risk_adjusted_score=0.60,
        trade_count=10,
        fees_total=3.0,
        created_at="2026-05-03T23:59:00Z",
        updated_at="2026-05-03T23:59:00Z",
    )
    upsert_daily_metric(
        conn,
        account_id=account_id,
        sleeve_id=sleeve_id,
        metric_date="2026-05-04",
        return_pct=0.4,
        drawdown_pct=-0.6,
        turnover_pct=2.1,
        slippage_bps=7.5,
        hit_rate=0.44,
        expectancy=0.07,
        risk_adjusted_score=0.55,
        trade_count=11,
        fees_total=3.2,
        created_at="2026-05-04T23:59:00Z",
        updated_at="2026-05-04T23:59:00Z",
    )


def test_run_for_account_sleeve_mode_applies_rotation_before_intent_generation(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_rotation"
    account_id = insert_repository_account(conn, name=account_name, strategy="trend")
    conn.execute(
        """
        UPDATE accounts
        SET rotation_schedule = ?,
            rotation_lookback_days = ?
        WHERE id = ?
        """,
        (
            dump_rotation_schedule(["trend", "meanrev"]),
            30,
            account_id,
        ),
    )
    conn.commit()
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_rotation",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        effective_from="2026-05-03T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    _insert_rotation_metric_rows(conn, account_id=account_id, sleeve_id=sleeve_id)
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)

    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-05T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(
        "trading.services.sleeves.shadow_evaluation.fetch_strategy_backtest_returns",
        lambda *_args, **_kwargs: [("meanrev", 1.0)] * 30,
    )
    captured = {"active_strategy": None}

    def _capture_intents(*_args, **_kwargs):
        assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        captured["active_strategy"] = (
            str(assignment["strategy_name"]).strip()
            if assignment is not None and assignment["strategy_name"] is not None
            else None
        )
        return []

    monkeypatch.setattr(runtime_service, "generate_sleeve_trade_intents", _capture_intents)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    assert captured["active_strategy"] == "meanrev"
    latest_decision = conn.execute(
        """
        SELECT rotation_action, selected_strategy
        FROM rotation_decisions
        WHERE sleeve_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (sleeve_id,),
    ).fetchone()
    assert latest_decision is not None
    assert latest_decision["rotation_action"] == "rotate"
    assert latest_decision["selected_strategy"] == "meanrev"


def test_run_for_account_sleeve_mode_respects_rotation_cooldown(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_rotation_cooldown"
    account_id = insert_repository_account(conn, name=account_name, strategy="trend")
    conn.execute(
        """
        UPDATE accounts
        SET rotation_schedule = ?,
            rotation_lookback_days = ?
        WHERE id = ?
        """,
        (
            dump_rotation_schedule(["trend", "meanrev"]),
            30,
            account_id,
        ),
    )
    conn.commit()
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_rotation_cooldown",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        effective_from="2026-05-03T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    _insert_rotation_metric_rows(conn, account_id=account_id, sleeve_id=sleeve_id)
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)
    conn.execute(
        """
        INSERT INTO rotation_decisions (
            sleeve_id, decision_time, incumbent_strategy, challenger_strategy,
            selected_strategy, rotation_action, cooldown_active, score_components_json,
            gate_results_json, decision_reason, config_version, param_set_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, 'rotate', 0, '{}', '{}', ?, ?, NULL, ?)
        """,
        (
            sleeve_id,
            "2026-05-05T10:00:00Z",
            "trend",
            "meanrev",
            "meanrev",
            "rotate_to_challenger",
            "cfg-old",
            "2026-05-05T10:00:00Z",
        ),
    )
    conn.commit()

    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-05T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(
        "trading.services.sleeves.shadow_evaluation.fetch_strategy_backtest_returns",
        lambda *_args, **_kwargs: [("meanrev", 1.0)] * 30,
    )
    captured = {"active_strategy": None}

    def _capture_intents(*_args, **_kwargs):
        assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        captured["active_strategy"] = (
            str(assignment["strategy_name"]).strip()
            if assignment is not None and assignment["strategy_name"] is not None
            else None
        )
        return []

    monkeypatch.setattr(runtime_service, "generate_sleeve_trade_intents", _capture_intents)

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    assert captured["active_strategy"] == "trend"
    latest_decision = conn.execute(
        """
        SELECT rotation_action, decision_reason, cooldown_active
        FROM rotation_decisions
        WHERE sleeve_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (sleeve_id,),
    ).fetchone()
    assert latest_decision is not None
    assert latest_decision["rotation_action"] == "hold"
    assert latest_decision["decision_reason"] == "cooldown_active"
    assert int(latest_decision["cooldown_active"]) == 1


def test_run_for_account_sleeve_mode_submits_and_persists_orders(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    account = get_account(conn, account_name)
    broker = FakeBroker()
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)

    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=1,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 1
    order_row = conn.execute(
        """
        SELECT sleeve_id, strategy_name, symbol, side, qty, status, broker_order_id
        FROM sleeve_orders
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert order_row is not None
    assert int(order_row["sleeve_id"]) == sleeve_id
    assert order_row["strategy_name"] == "trend"
    assert order_row["symbol"] == "AAPL"
    assert order_row["side"] == "buy"
    assert float(order_row["qty"]) == 1.0
    assert order_row["status"] == "filled"
    assert order_row["broker_order_id"] == "fake-broker-order"

    fill_count = conn.execute(
        "SELECT COUNT(*) AS n FROM sleeve_fills WHERE sleeve_id = ?",
        (sleeve_id,),
    ).fetchone()
    assert fill_count is not None
    assert int(fill_count["n"]) == 1

    trade_count = conn.execute(
        "SELECT COUNT(*) AS n FROM trades WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert trade_count is not None
    assert int(trade_count["n"]) == 1

    sleeve_row = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
    assert sleeve_row is not None
    assert float(sleeve_row["current_cash"]) == 900.0
    assert float(sleeve_row["current_equity"]) == 1_000.0

    risk_snapshot = conn.execute(
        """
        SELECT max_symbol_concentration_pct, max_sector_concentration_pct
        FROM portfolio_risk_snapshots
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
        FROM sleeve_risk_decisions
        WHERE account_id = ?
        ORDER BY id ASC
        """,
        (account_id,),
    ).fetchall()
    assert len(decision_rows) >= 1
    assert decision_rows[0]["action"] == "allow"

    broker.place_order.assert_called_once()
    broker.disconnect.assert_called_once()


def test_run_for_account_sleeve_mode_applies_risk_rescale_before_submit(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_rescale"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_rescale",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    broker = FakeBroker()
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)

    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=5,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 1
    broker.place_order.assert_called_once()
    broker_order = broker.place_order.call_args.args[0]
    assert broker_order.qty == 2.0

    order_row = conn.execute(
        "SELECT qty FROM sleeve_orders WHERE account_id = ? ORDER BY id DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    assert order_row is not None
    assert float(order_row["qty"]) == 2.0
    rescale_row = conn.execute(
        """
        SELECT action, reason_code, requested_qty, approved_qty
        FROM sleeve_risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert rescale_row is not None
    assert rescale_row["action"] == "rescale"
    assert rescale_row["reason_code"] == "sleeve_notional_cap"
    assert int(rescale_row["requested_qty"]) == 5
    assert int(rescale_row["approved_qty"]) == 2


def test_run_for_account_sleeve_mode_kill_switch_stale_price_blocks_submission(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_stale"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_stale",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)

    broker = FakeBroker()
    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=1,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 0.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM portfolio_risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "stale_price_data" in payload["kill_switch_reasons"]
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM sleeve_risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert decision_row is not None
    assert decision_row["action"] == "block"
    assert decision_row["reason_code"] == "stale_price_data"


def test_run_for_account_sleeve_mode_kill_switch_reconciliation_mismatch(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_recon"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_recon",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    broker = FakeBroker()

    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "reconcile_sleeves_vs_latest_snapshot",
        lambda *_args, **_kwargs: SleeveEquityReconciliationResult(
            account_id=account_id,
            account_equity=1000.0,
            total_sleeve_equity=900.0,
            equity_difference=-100.0,
            tolerance=0.01,
            within_tolerance=False,
            snapshot_time="2026-05-03T13:59:00Z",
        ),
    )
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=1,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM portfolio_risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "reconciliation_mismatch" in payload["kill_switch_reasons"]
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM sleeve_risk_decisions
        WHERE account_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (account_id,),
    ).fetchone()
    assert decision_row is not None
    assert decision_row["action"] == "block"
    assert decision_row["reason_code"] == "reconciliation_mismatch"


def test_run_for_account_sleeve_mode_kill_switch_broker_anomaly(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_broker_anomaly"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_anomaly",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )
    _insert_matching_snapshot(conn, account_id=account_id, equity=1_000.0)

    class _FailingBroker:
        def __init__(self) -> None:
            self.disconnect_calls = 0

        def place_order(self, _order):
            raise RuntimeError("ib anomaly")

        def disconnect(self) -> None:
            self.disconnect_calls += 1

    broker = _FailingBroker()
    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=1,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM portfolio_risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "broker_api_anomaly" in payload["kill_switch_reasons"]
    sleeve_order_status = conn.execute(
        "SELECT status FROM sleeve_orders WHERE account_id = ? ORDER BY id DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    assert sleeve_order_status is not None
    assert sleeve_order_status["status"] == "rejected"
    decision_row = conn.execute(
        """
        SELECT action, reason_code
        FROM sleeve_risk_decisions
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


def test_run_for_account_sleeve_mode_kill_switch_stale_reconciliation_snapshot(conn, monkeypatch) -> None:
    account_name = "acct_runtime_sleeve_stale_snapshot"
    account_id = insert_repository_account(conn, name=account_name)
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core_stale_snapshot",
        status="active",
        base_ccy="USD",
        start_equity=1_000.0,
        current_cash=1_000.0,
        current_equity=1_000.0,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    insert_snapshot_row(
        conn,
        account_id=account_id,
        snapshot_time="2026-05-01T00:00:00Z",
        cash=1_000.0,
        market_value=0.0,
        equity=1_000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )

    broker = FakeBroker()
    monkeypatch.setattr(runtime_service, "_is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "utc_now_iso", lambda: "2026-05-03T14:00:00Z")
    monkeypatch.setattr(
        runtime_service,
        "_rotate_runtime_account",
        lambda _conn, _account_name, account_row, _now_iso: account_row,
    )
    monkeypatch.setattr(runtime_service, "get_broker_for_account", lambda _account: broker)
    monkeypatch.setattr(
        runtime_service,
        "generate_sleeve_trade_intents",
        lambda *_args, **_kwargs: [
            SleeveTradeIntent(
                account_id=account_id,
                sleeve_id=sleeve_id,
                strategy_name="trend",
                param_set_id=None,
                side="buy",
                symbol="AAPL",
                qty=1,
                requested_price=100.0,
                forced_sell=None,
                delta_est=None,
                iv_est=None,
            )
        ],
    )

    executed = run_for_account(
        conn,
        account_name=account_name,
        universe=["AAPL"],
        prices={"AAPL": 100.0},
        iv_rank_proxy={},
        min_trades=1,
        max_trades=1,
        fee=0.0,
        execution_mode="sleeve",
    )

    assert executed == 0
    broker.place_order.assert_not_called()
    row = conn.execute(
        "SELECT kill_switch_triggered, risk_payload_json FROM portfolio_risk_snapshots WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    assert row is not None
    assert int(row["kill_switch_triggered"]) == 1
    payload = json.loads(row["risk_payload_json"])
    assert "stale_reconciliation_snapshot" in payload["kill_switch_reasons"]
