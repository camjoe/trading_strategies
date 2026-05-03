from __future__ import annotations

import pytest

from trading.repositories.sleeve_ledger import fetch_sleeve_ledger_sum_by_type
from trading.repositories.sleeve_orders import fetch_sleeve_fills_for_order, insert_sleeve_order
from trading.repositories.sleeve_positions import fetch_sleeve_position
from trading.repositories.sleeves import fetch_strategy_sleeve_by_id, insert_strategy_sleeve
from trading.services.sleeves.accounting import apply_sleeve_fill
from tests.support.repositories import insert_repository_account


def _seed_sleeve(conn, *, account_id: int, cash: float, equity: float) -> int:
    return insert_strategy_sleeve(
        conn,
        account_id=account_id,
        name="core",
        status="active",
        base_ccy="USD",
        start_equity=equity,
        current_cash=cash,
        current_equity=equity,
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )


def _seed_sleeve_order(
    conn,
    *,
    account_id: int,
    sleeve_id: int,
    side: str,
    qty: float,
    requested_price: float,
    symbol: str = "SPY",
) -> int:
    return insert_sleeve_order(
        conn,
        account_id=account_id,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=None,
        rotation_decision_id=None,
        broker_order_id="ib-1",
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="market",
        time_in_force="day",
        requested_price=requested_price,
        status="Submitted",
        config_version="cfg-v1",
        submitted_at="2026-05-03T10:00:00Z",
        updated_at="2026-05-03T10:00:00Z",
    )


def test_apply_sleeve_fill_buy_updates_fill_position_ledger_and_balances(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_buy")
    sleeve_id = _seed_sleeve(conn, account_id=account_id, cash=10_000.0, equity=10_000.0)
    sleeve_order_id = _seed_sleeve_order(
        conn,
        account_id=account_id,
        sleeve_id=sleeve_id,
        side="buy",
        qty=10.0,
        requested_price=500.0,
    )

    result = apply_sleeve_fill(
        conn,
        sleeve_order_id=sleeve_order_id,
        broker_fill_id="fill-1",
        exec_id="exec-1",
        filled_qty=10.0,
        fill_price=501.0,
        commission=1.0,
        fill_time="2026-05-03T10:01:00Z",
        updated_at="2026-05-03T10:01:00Z",
    )

    assert result.applied is True
    assert result.transition is not None
    assert result.transition.slippage_amount == pytest.approx(10.0)

    fills = fetch_sleeve_fills_for_order(conn, sleeve_order_id=sleeve_order_id)
    assert len(fills) == 1

    position = fetch_sleeve_position(conn, sleeve_id=sleeve_id, symbol="SPY")
    assert position is not None
    assert float(position["qty"]) == pytest.approx(10.0)
    assert float(position["avg_cost"]) == pytest.approx(501.1)
    assert float(position["market_value"]) == pytest.approx(5_010.0)
    assert float(position["unrealized_pnl"]) == pytest.approx(-1.0)

    sleeve = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
    assert sleeve is not None
    assert float(sleeve["current_cash"]) == pytest.approx(4_989.0)
    assert float(sleeve["current_equity"]) == pytest.approx(9_999.0)

    cash_total = fetch_sleeve_ledger_sum_by_type(
        conn,
        sleeve_id=sleeve_id,
        entry_type="cash_movement",
    )
    fee_total = fetch_sleeve_ledger_sum_by_type(
        conn,
        sleeve_id=sleeve_id,
        entry_type="fee",
    )
    assert cash_total == pytest.approx(-5_011.0)
    assert fee_total == pytest.approx(-1.0)


def test_apply_sleeve_fill_sell_updates_realized_and_handles_duplicates(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_sell")
    sleeve_id = _seed_sleeve(conn, account_id=account_id, cash=200.0, equity=1_200.0)
    conn.execute(
        """
        INSERT INTO sleeve_positions (sleeve_id, symbol, qty, avg_cost, market_value, unrealized_pnl, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sleeve_id, "QQQ", 10.0, 100.0, 1_000.0, 0.0, "2026-05-03T09:59:00Z"),
    )
    conn.commit()
    sleeve_order_id = _seed_sleeve_order(
        conn,
        account_id=account_id,
        sleeve_id=sleeve_id,
        side="sell",
        qty=4.0,
        requested_price=105.0,
        symbol="QQQ",
    )

    first = apply_sleeve_fill(
        conn,
        sleeve_order_id=sleeve_order_id,
        broker_fill_id="fill-2",
        exec_id="exec-2",
        filled_qty=4.0,
        fill_price=110.0,
        commission=2.0,
        fill_time="2026-05-03T10:02:00Z",
        updated_at="2026-05-03T10:02:00Z",
    )
    second = apply_sleeve_fill(
        conn,
        sleeve_order_id=sleeve_order_id,
        broker_fill_id="fill-2",
        exec_id="exec-2",
        filled_qty=4.0,
        fill_price=110.0,
        commission=2.0,
        fill_time="2026-05-03T10:02:00Z",
        updated_at="2026-05-03T10:02:00Z",
    )

    assert first.applied is True
    assert first.transition is not None
    assert first.transition.realized_pnl_delta == pytest.approx(38.0)
    assert second.applied is False
    assert second.reason == "duplicate_exec_id"

    fills = fetch_sleeve_fills_for_order(conn, sleeve_order_id=sleeve_order_id)
    assert len(fills) == 1

    position = fetch_sleeve_position(conn, sleeve_id=sleeve_id, symbol="QQQ")
    assert position is not None
    assert float(position["qty"]) == pytest.approx(6.0)
    assert float(position["avg_cost"]) == pytest.approx(100.0)
    assert float(position["market_value"]) == pytest.approx(660.0)
    assert float(position["unrealized_pnl"]) == pytest.approx(60.0)

    realized_total = fetch_sleeve_ledger_sum_by_type(
        conn,
        sleeve_id=sleeve_id,
        entry_type="realized_pnl",
    )
    assert realized_total == pytest.approx(38.0)

    sleeve = fetch_strategy_sleeve_by_id(conn, sleeve_id=sleeve_id)
    assert sleeve is not None
    assert float(sleeve["current_cash"]) == pytest.approx(638.0)
    assert float(sleeve["current_equity"]) == pytest.approx(1_298.0)
