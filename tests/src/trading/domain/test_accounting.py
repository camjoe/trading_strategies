import pytest

from trading.domain.accounting import apply_buy, apply_sell, compute_account_state


class TestApplyBuy:
    """The shared buy primitive — the live replay and the backtest both fill through it."""

    def test_negative_qty_raises_value_error(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}

        with pytest.raises(ValueError, match="positive"):
            apply_buy("AAPL", -5.0, 100.0, 0.0, positions, avg_cost, 1000.0)

    def test_zero_qty_raises_value_error(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}

        with pytest.raises(ValueError, match="positive"):
            apply_buy("AAPL", 0.0, 100.0, 0.0, positions, avg_cost, 1000.0)

    def test_fractional_qty_raises_value_error(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}

        with pytest.raises(ValueError, match="whole units"):
            apply_buy("AAPL", 1.5, 100.0, 0.0, positions, avg_cost, 1000.0)

    def test_valid_buy_updates_position_and_avg_cost(self) -> None:
        positions = {"AAPL": 0.0}
        avg_cost = {"AAPL": 0.0}
        remaining_cash = apply_buy("AAPL", 2.0, 50.0, 1.0, positions, avg_cost, 200.0)

        assert positions["AAPL"] == pytest.approx(2.0)
        # Fee is capitalized: avg_cost = (0*0 + 2*50 + 1) / 2 = 50.5
        assert avg_cost["AAPL"] == pytest.approx(50.5)
        assert remaining_cash == pytest.approx(200.0 - (2.0 * 50.0 + 1.0))

    def test_buy_adds_to_existing_position(self) -> None:
        positions = {"AAPL": 3.0}
        avg_cost = {"AAPL": 40.0}
        apply_buy("AAPL", 2.0, 60.0, 0.0, positions, avg_cost, 500.0)

        assert positions["AAPL"] == pytest.approx(5.0)
        # avg_cost = (3*40 + 2*60) / 5 = 48.0
        assert avg_cost["AAPL"] == pytest.approx(48.0)


class TestApplySell:
    def test_sell_reduces_position_and_updates_realized_pnl(self) -> None:
        positions = {"AAPL": 5.0}
        avg_cost = {"AAPL": 40.0}
        cash, realized = apply_sell("AAPL", 2.0, 60.0, 1.0, positions, avg_cost, 100.0, 0.0)

        assert positions["AAPL"] == pytest.approx(3.0)
        # proceeds = 2*60 - 1 = 119; pnl = (60-40)*2 - 1 = 39
        assert cash == pytest.approx(219.0)
        assert realized == pytest.approx(39.0)

    def test_sell_all_flattens_position_and_keeps_avg_cost(self) -> None:
        # A closed position keeps its stale average cost rather than being zeroed
        # inline: nothing reads it at zero quantity, and _compact_positions drops
        # the key on the live path.
        positions = {"AAPL": 3.0}
        avg_cost = {"AAPL": 50.0}
        apply_sell("AAPL", 3.0, 50.0, 0.0, positions, avg_cost, 0.0, 0.0)

        assert positions["AAPL"] == pytest.approx(0.0)
        assert avg_cost["AAPL"] == pytest.approx(50.0)

    def test_overselling_raises_rather_than_going_negative(self) -> None:
        positions = {"AAPL": 2.0}
        avg_cost = {"AAPL": 50.0}

        with pytest.raises(ValueError, match="trying to sell"):
            apply_sell("AAPL", 3.0, 60.0, 0.0, positions, avg_cost, 0.0, 0.0)


class TestComputeAccountState:
    def test_buy_sell_realized_pnl(self) -> None:
        trades = [
            {"ticker": "AAPL", "side": "buy", "qty": 10, "price": 100, "fee": 1},
            {"ticker": "AAPL", "side": "sell", "qty": 4, "price": 110, "fee": 1},
        ]

        state = compute_account_state(initial_cash=1000.0, trades=trades)

        assert state.positions == {"AAPL": 6.0}
        assert state.avg_cost["AAPL"] == pytest.approx(100.1)
        assert state.cash == pytest.approx(438.0)
        assert state.realized_pnl == pytest.approx(38.6)

    def test_rejects_non_positive_qty(self) -> None:
        with pytest.raises(ValueError, match="Trade quantity must be > 0"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "buy", "qty": 0, "price": 100, "fee": 1}],
            )

    def test_rejects_non_positive_price(self) -> None:
        with pytest.raises(ValueError, match="Trade price must be > 0"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "buy", "qty": 1, "price": 0, "fee": 1}],
            )

    def test_rejects_invalid_side(self) -> None:
        with pytest.raises(ValueError, match="Unsupported side: hold"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "hold", "qty": 1, "price": 100, "fee": 1}],
            )

    def test_rejects_sell_above_holdings(self) -> None:
        with pytest.raises(ValueError, match="Invalid sell for AAPL"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "sell", "qty": 1, "price": 100, "fee": 1}],
            )

    def test_sell_all_removes_position_and_avg_cost(self) -> None:
        state = compute_account_state(
            initial_cash=1000.0,
            trades=[
                {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                {"ticker": "AAPL", "side": "sell", "qty": 2, "price": 110, "fee": 0},
            ],
        )

        assert state.positions == {}
        assert state.avg_cost == {}
        assert state.realized_pnl == pytest.approx(20.0)
        assert state.cash == pytest.approx(1020.0)

    def test_rebuying_a_sold_out_position_starts_a_fresh_cost_basis(self) -> None:
        # The prior cost basis must not blend into the new one. Nothing clears
        # avg_cost when a position closes; at zero quantity the weighting term
        # (old_qty * avg_cost) is zero, so the reset would be inert.
        state = compute_account_state(
            initial_cash=1000.0,
            trades=[
                {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                {"ticker": "AAPL", "side": "sell", "qty": 2, "price": 110, "fee": 0},
                {"ticker": "AAPL", "side": "buy", "qty": 1, "price": 50, "fee": 0},
            ],
        )

        assert state.positions == {"AAPL": 1.0}
        assert state.avg_cost["AAPL"] == pytest.approx(50.0)
        assert state.cash == pytest.approx(970.0)

    def test_multiple_buys_updates_weighted_avg_cost(self) -> None:
        state = compute_account_state(
            initial_cash=1000.0,
            trades=[
                {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                {"ticker": "AAPL", "side": "buy", "qty": 1, "price": 130, "fee": 1},
            ],
        )

        assert state.positions == {"AAPL": 3.0}
        assert state.avg_cost["AAPL"] == pytest.approx((200.0 + 131.0) / 3.0)
        assert state.cash == pytest.approx(669.0)
        assert state.total_deposited == pytest.approx(0.0)


class TestWholeUnitQuantities:
    """Instrument quantities must be whole units — the flat test in ``_compact_positions``
    (``qty > 0``) reads a fractional remainder as a phantom open position."""

    def test_rejects_fractional_buy(self) -> None:
        with pytest.raises(ValueError, match="whole units"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[{"ticker": "AAPL", "side": "buy", "qty": 0.5, "price": 100, "fee": 0}],
            )

    def test_rejects_fractional_sell(self) -> None:
        with pytest.raises(ValueError, match="whole units"):
            compute_account_state(
                initial_cash=1000.0,
                trades=[
                    {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
                    {"ticker": "AAPL", "side": "sell", "qty": 1.5, "price": 110, "fee": 0},
                ],
            )

    def test_cash_movements_are_exempt(self) -> None:
        # Deposits ride the settlement ticker as qty=dollars, price=1.0, and are
        # genuinely fractional. They return before the position math.
        state = compute_account_state(
            initial_cash=0.0,
            trades=[
                {"ticker": "CASH", "side": "buy", "qty": 1234.56, "price": 1.0, "fee": 0.0},
                {"ticker": "CASH", "side": "sell", "qty": 34.56, "price": 1.0, "fee": 0.0},
            ],
        )

        assert state.cash == pytest.approx(1200.0)
        assert state.total_deposited == pytest.approx(1234.56)
        assert state.positions == {}


class TestSettlementTickerDepositModel:
    def test_cash_buy_is_deposit_adds_to_cash(self) -> None:
        trades = [{"ticker": "CASH", "side": "buy", "qty": 1000.0, "price": 1.0, "fee": 0.0}]
        state = compute_account_state(initial_cash=0.0, trades=trades)

        assert state.cash == pytest.approx(1000.0)
        assert state.total_deposited == pytest.approx(1000.0)

    def test_cash_buy_does_not_create_position(self) -> None:
        trades = [{"ticker": "CASH", "side": "buy", "qty": 500.0, "price": 1.0, "fee": 0.0}]
        state = compute_account_state(initial_cash=0.0, trades=trades)

        assert "CASH" not in state.positions

    def test_multiple_cash_deposits_accumulate(self) -> None:
        trades = [
            {"ticker": "CASH", "side": "buy", "qty": 1000.0, "price": 1.0, "fee": 0.0},
            {"ticker": "CASH", "side": "buy", "qty": 500.0, "price": 1.0, "fee": 0.0},
        ]
        state = compute_account_state(initial_cash=0.0, trades=trades)

        assert state.cash == pytest.approx(1500.0)
        assert state.total_deposited == pytest.approx(1500.0)

    def test_deposit_then_equity_buy(self) -> None:
        trades = [
            {"ticker": "CASH", "side": "buy", "qty": 1000.0, "price": 1.0, "fee": 0.0},
            {"ticker": "AAPL", "side": "buy", "qty": 5.0, "price": 100.0, "fee": 0.0},
        ]
        state = compute_account_state(initial_cash=0.0, trades=trades)

        assert state.cash == pytest.approx(500.0)
        assert state.total_deposited == pytest.approx(1000.0)
        assert state.positions == {"AAPL": 5.0}
        assert "CASH" not in state.positions

    def test_cash_sell_is_withdrawal(self) -> None:
        trades = [
            {"ticker": "CASH", "side": "buy", "qty": 1000.0, "price": 1.0, "fee": 0.0},
            {"ticker": "CASH", "side": "sell", "qty": 200.0, "price": 1.0, "fee": 0.0},
        ]
        state = compute_account_state(initial_cash=0.0, trades=trades)

        assert state.cash == pytest.approx(800.0)
        assert state.total_deposited == pytest.approx(1000.0)

    def test_settlement_ticker_none_treats_cash_as_equity(self) -> None:
        trades = [{"ticker": "CASH", "side": "buy", "qty": 100.0, "price": 1.0, "fee": 0.0}]
        state = compute_account_state(initial_cash=200.0, trades=trades, settlement_ticker=None)

        assert state.positions == {"CASH": 100.0}
        assert state.cash == pytest.approx(100.0)
        assert state.total_deposited == pytest.approx(0.0)

    def test_equity_only_account_has_zero_total_deposited(self) -> None:
        trades = [
            {"ticker": "AAPL", "side": "buy", "qty": 2, "price": 100, "fee": 0},
            {"ticker": "AAPL", "side": "sell", "qty": 1, "price": 110, "fee": 0},
        ]
        state = compute_account_state(initial_cash=500.0, trades=trades)

        assert state.total_deposited == pytest.approx(0.0)
