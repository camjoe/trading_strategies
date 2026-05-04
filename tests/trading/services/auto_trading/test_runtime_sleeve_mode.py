from __future__ import annotations

import json

from trading.repositories.snapshots import insert_snapshot_row
from trading.repositories.sleeves import fetch_strategy_sleeve_by_id, insert_strategy_sleeve
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
    assert broker.disconnect_calls == 1
