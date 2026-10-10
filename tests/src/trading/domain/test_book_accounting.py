from __future__ import annotations

from decimal import Decimal

import pytest

from trading.domain.accounting.book import apply_book_fill_transition


def test_buy_fill_updates_cash_avg_cost_and_slippage() -> None:
    transition = apply_book_fill_transition(
        side="buy",
        symbol="spy",
        qty=Decimal("10"),
        fill_price=Decimal("101.0"),
        commission=Decimal("2.0"),
        requested_price=Decimal("100.5"),
        position_qty=Decimal("0"),
        position_avg_cost=Decimal("0"),
        cash=Decimal("2000.0"),
        realized_pnl=Decimal("0"),
    )

    assert transition.symbol == "SPY"
    assert float(transition.cash_delta) == pytest.approx(-1_012.0)
    assert float(transition.ending_qty) == pytest.approx(10.0)
    assert float(transition.ending_avg_cost) == pytest.approx(101.2)
    assert float(transition.ending_cash) == pytest.approx(988.0)
    assert float(transition.ending_market_value) == pytest.approx(1_010.0)
    assert float(transition.ending_unrealized_pnl) == pytest.approx(-2.0)
    assert float(transition.slippage_amount) == pytest.approx(5.0)


def test_sell_fill_updates_realized_and_preserves_avg_cost_for_remainder() -> None:
    transition = apply_book_fill_transition(
        side="sell",
        symbol="QQQ",
        qty=Decimal("4"),
        fill_price=Decimal("110.0"),
        commission=Decimal("2.0"),
        requested_price=Decimal("105.0"),
        position_qty=Decimal("10"),
        position_avg_cost=Decimal("100.0"),
        cash=Decimal("500.0"),
        realized_pnl=Decimal("10.0"),
    )

    assert float(transition.cash_delta) == pytest.approx(438.0)
    assert float(transition.realized_pnl_delta) == pytest.approx(38.0)
    assert float(transition.ending_realized_pnl) == pytest.approx(48.0)
    assert float(transition.ending_qty) == pytest.approx(6.0)
    assert float(transition.ending_avg_cost) == pytest.approx(100.0)
    assert float(transition.ending_market_value) == pytest.approx(660.0)
    assert float(transition.ending_unrealized_pnl) == pytest.approx(60.0)
    assert float(transition.ending_equity) == pytest.approx(1_598.0)
    assert float(transition.slippage_amount) == pytest.approx(-20.0)


def test_rejects_sell_above_holdings() -> None:
    with pytest.raises(ValueError, match="Invalid sell for AAPL"):
        apply_book_fill_transition(
            side="sell",
            symbol="AAPL",
            qty=Decimal("2"),
            fill_price=Decimal("100.0"),
            commission=Decimal("0"),
            requested_price=None,
            position_qty=Decimal("1"),
            position_avg_cost=Decimal("90.0"),
            cash=Decimal("100.0"),
            realized_pnl=Decimal("0"),
        )
