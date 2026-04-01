from __future__ import annotations

import pytest

from trading.backtesting.domain.simulation_math import (
    compute_market_value,
    compute_unrealized_pnl,
    update_on_buy,
    update_on_sell,
)


def test_market_value_and_unrealized_pnl_ignore_missing_or_non_positive_positions() -> None:
    positions = {"AAPL": 2.0, "MSFT": 1.5, "NVDA": 0.0}
    prices = {"AAPL": 10.0, "MSFT": 20.0}
    avg_cost = {"AAPL": 8.0, "MSFT": 25.0, "NVDA": 100.0}

    assert compute_market_value(positions, prices) == pytest.approx(50.0)
    assert compute_unrealized_pnl(positions, avg_cost, prices) == pytest.approx(-3.5)


class TestUpdateOnBuyGuard:
    """update_on_buy must raise rather than silently produce NaN avg_cost
    when a non-positive qty would make the resulting position non-positive."""

    def test_negative_qty_raises_value_error(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}

        with pytest.raises(ValueError, match="positive"):
            update_on_buy("AAPL", -5.0, 100.0, 0.0, positions, avg_cost, 1000.0)

    def test_zero_qty_raises_value_error(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}

        with pytest.raises(ValueError, match="positive"):
            update_on_buy("AAPL", 0.0, 100.0, 0.0, positions, avg_cost, 1000.0)

    def test_valid_buy_updates_position_and_avg_cost(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}
        remaining_cash = update_on_buy("AAPL", 2.0, 50.0, 1.0, positions, avg_cost, 200.0)

        assert positions["AAPL"] == pytest.approx(2.0)
        # avg_cost = (0*0 + 2*50 + 1) / 2 = 101/2 = 50.5
        assert avg_cost["AAPL"] == pytest.approx(50.5)
        assert remaining_cash == pytest.approx(200.0 - (2.0 * 50.0 + 1.0))

    def test_buy_adds_to_existing_position(self) -> None:
        positions = {"AAPL": 3.0}
        avg_cost = {"AAPL": 40.0}
        update_on_buy("AAPL", 2.0, 60.0, 0.0, positions, avg_cost, 500.0)

        assert positions["AAPL"] == pytest.approx(5.0)
        # avg_cost = (3*40 + 2*60) / 5 = (120 + 120) / 5 = 48.0
        assert avg_cost["AAPL"] == pytest.approx(48.0)


class TestUpdateOnSell:
    def test_sell_reduces_position_and_updates_realized_pnl(self) -> None:
        positions = {"AAPL": 5.0}
        avg_cost = {"AAPL": 40.0}
        cash, realized_pnl = update_on_sell("AAPL", 2.0, 60.0, 1.0, positions, avg_cost, 100.0, 0.0)

        assert positions["AAPL"] == pytest.approx(3.0)
        # proceeds = 2*60 - 1 = 119; pnl = (60-40)*2 - 1 = 39
        assert cash == pytest.approx(219.0)
        assert realized_pnl == pytest.approx(39.0)

    def test_sell_all_zeroes_position_and_avg_cost(self) -> None:
        positions = {"AAPL": 3.0}
        avg_cost = {"AAPL": 50.0}
        update_on_sell("AAPL", 3.0, 50.0, 0.0, positions, avg_cost, 0.0, 0.0)

        assert positions["AAPL"] == pytest.approx(0.0)
        assert avg_cost["AAPL"] == pytest.approx(0.0)
