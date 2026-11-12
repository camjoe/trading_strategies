from decimal import Decimal

import pytest

from trading.domain.accounting.holdings import Holdings


class TestStartingWith:
    def test_float_cash_gives_float_zeros(self) -> None:
        holdings = Holdings.starting_with(1000.0)

        assert holdings.cash == 1000.0
        assert holdings.realized_pnl == 0.0
        assert isinstance(holdings.positions["AAPL"], float)
        assert isinstance(holdings.avg_cost["AAPL"], float)

    def test_decimal_cash_gives_decimal_zeros(self) -> None:
        holdings = Holdings.starting_with(Decimal("1000"))

        assert holdings.realized_pnl == Decimal("0")
        assert holdings.positions["AAPL"] == Decimal("0")
        assert isinstance(holdings.positions["AAPL"], Decimal)


class TestBuy:
    def test_negative_qty_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Holdings.starting_with(1000.0).buy("AAPL", -5.0, 100.0, 0.0)

    def test_zero_qty_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Holdings.starting_with(1000.0).buy("AAPL", 0.0, 100.0, 0.0)

    def test_fractional_qty_is_allowed(self) -> None:
        holdings = Holdings.starting_with(1000.0)
        holdings.buy("AAPL", 1.5, 100.0, 0.0)

        assert holdings.positions["AAPL"] == pytest.approx(1.5)
        assert holdings.cash == pytest.approx(850.0)

    def test_fee_is_capitalized_into_avg_cost(self) -> None:
        holdings = Holdings.starting_with(200.0)
        holdings.buy("AAPL", 2.0, 50.0, 1.0)

        assert holdings.positions["AAPL"] == pytest.approx(2.0)
        # avg_cost = (0*0 + 2*50 + 1) / 2 = 50.5
        assert holdings.avg_cost["AAPL"] == pytest.approx(50.5)
        assert holdings.cash == pytest.approx(200.0 - (2.0 * 50.0 + 1.0))

    def test_buy_re_averages_an_existing_position(self) -> None:
        holdings = Holdings.starting_with(500.0)
        holdings.buy("AAPL", 3.0, 40.0, 0.0)
        holdings.buy("AAPL", 2.0, 60.0, 0.0)

        assert holdings.positions["AAPL"] == pytest.approx(5.0)
        # avg_cost = (3*40 + 2*60) / 5 = 48.0
        assert holdings.avg_cost["AAPL"] == pytest.approx(48.0)

    def test_decimal_buy_is_exact(self) -> None:
        holdings = Holdings.starting_with(Decimal("100"))
        holdings.buy("AAPL", Decimal("3"), Decimal("10.01"), Decimal("0"))

        assert holdings.positions["AAPL"] == Decimal("3")
        assert holdings.avg_cost["AAPL"] == Decimal("10.01")
        assert holdings.cash == Decimal("69.97")


class TestSell:
    def _holding(self, qty: float, avg_cost: float, cash: float = 100.0) -> Holdings[float]:
        holdings = Holdings.starting_with(cash)
        holdings.positions["AAPL"] = qty
        holdings.avg_cost["AAPL"] = avg_cost
        return holdings

    def test_sell_reduces_position_and_books_realized_pnl(self) -> None:
        holdings = self._holding(5.0, 40.0)
        holdings.sell("AAPL", 2.0, 60.0, 1.0)

        assert holdings.positions["AAPL"] == pytest.approx(3.0)
        # proceeds = 2*60 - 1 = 119; pnl = (60-40)*2 - 1 = 39
        assert holdings.cash == pytest.approx(219.0)
        assert holdings.realized_pnl == pytest.approx(39.0)

    def test_realized_pnl_accumulates(self) -> None:
        holdings = self._holding(5.0, 40.0)
        holdings.sell("AAPL", 2.0, 60.0, 0.0)
        holdings.sell("AAPL", 1.0, 50.0, 0.0)

        assert holdings.realized_pnl == pytest.approx(40.0 + 10.0)

    def test_sell_all_flattens_position_and_keeps_avg_cost(self) -> None:
        holdings = self._holding(3.0, 50.0, cash=0.0)
        holdings.sell("AAPL", 3.0, 50.0, 0.0)

        assert holdings.positions["AAPL"] == pytest.approx(0.0)
        assert holdings.avg_cost["AAPL"] == pytest.approx(50.0)

    def test_overselling_raises_and_changes_nothing(self) -> None:
        holdings = self._holding(2.0, 50.0, cash=0.0)

        with pytest.raises(ValueError, match="trying to sell"):
            holdings.sell("AAPL", 3.0, 60.0, 0.0)

        assert holdings.positions["AAPL"] == 2.0
        assert holdings.cash == 0.0

    def test_decimal_sell_is_exact(self) -> None:
        holdings = Holdings.starting_with(Decimal("0"))
        holdings.positions["AAPL"] = Decimal("3")
        holdings.avg_cost["AAPL"] = Decimal("10.01")
        holdings.sell("AAPL", Decimal("3"), Decimal("11"), Decimal("0"))

        assert holdings.cash == Decimal("33")
        assert holdings.realized_pnl == Decimal("2.97")


class TestOpenPositions:
    def test_drops_sold_out_tickers_and_their_avg_cost(self) -> None:
        holdings = Holdings.starting_with(Decimal("1000"))
        holdings.buy("AAPL", Decimal("2"), Decimal("10"), Decimal("0"))
        holdings.buy("MSFT", Decimal("1"), Decimal("20"), Decimal("0"))
        holdings.sell("AAPL", Decimal("2"), Decimal("12"), Decimal("0"))

        positions, avg_cost = holdings.open_positions()

        assert positions == {"MSFT": Decimal("1")}
        assert avg_cost == {"MSFT": Decimal("20")}

    def test_fractional_round_trip_leaves_no_phantom_position(self) -> None:
        holdings = Holdings.starting_with(1000.0)
        holdings.buy("AAPL", 0.1, 10.0, 0.0)
        holdings.sell("AAPL", 0.1, 10.0, 0.0)

        assert holdings.open_positions() == ({}, {})
