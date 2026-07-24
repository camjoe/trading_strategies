from __future__ import annotations

import pytest

from trading.domain.daily_metrics import DailyTrade, compute_daily_book_metrics


def _buy(qty=10.0, fill=100.0, requested=100.0, commission=0.0) -> DailyTrade:
    return DailyTrade(
        side="buy", filled_qty=qty, avg_fill_price=fill, requested_price=requested, commission=commission
    )


def _sell(qty=10.0, fill=100.0, requested=100.0, commission=0.0, pnl=None) -> DailyTrade:
    return DailyTrade(
        side="sell",
        filled_qty=qty,
        avg_fill_price=fill,
        requested_price=requested,
        commission=commission,
        realized_pnl_delta=pnl,
    )


class TestReturnPct:
    def test_computed_from_equity_boundaries(self) -> None:
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1020.0, trades=[])
        assert m.return_pct == pytest.approx(2.0)

    def test_none_without_prior_equity(self) -> None:
        # A book's first day has no previous snapshot, so return is unknowable.
        m = compute_daily_book_metrics(prev_equity=None, end_equity=1020.0, trades=[])
        assert m.return_pct is None

    def test_none_when_prior_equity_is_zero(self) -> None:
        m = compute_daily_book_metrics(prev_equity=0.0, end_equity=1020.0, trades=[])
        assert m.return_pct is None


class TestTradeAggregates:
    def test_zero_trade_day_is_flat_not_null(self) -> None:
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1000.0, trades=[])
        assert m.trade_count == 0
        assert m.fees_total == 0.0
        assert m.turnover_pct is None  # no trades → no turnover
        assert m.slippage_bps is None

    def test_trade_count_and_fees_sum(self) -> None:
        m = compute_daily_book_metrics(
            prev_equity=1000.0,
            end_equity=1000.0,
            trades=[_buy(commission=1.5), _sell(commission=2.0)],
        )
        assert m.trade_count == 2
        assert m.fees_total == pytest.approx(3.5)

    def test_turnover_is_notional_over_equity(self) -> None:
        # one 10 x $100 buy against $2000 equity → $1000 notional → 50%
        m = compute_daily_book_metrics(prev_equity=2000.0, end_equity=2000.0, trades=[_buy(qty=10.0, fill=100.0)])
        assert m.turnover_pct == pytest.approx(50.0)


class TestSlippage:
    def test_buy_filled_above_requested_is_positive_cost(self) -> None:
        # paid 101 vs requested 100 → +100 bps of cost
        m = compute_daily_book_metrics(prev_equity=1.0, end_equity=1.0, trades=[_buy(fill=101.0, requested=100.0)])
        assert m.slippage_bps == pytest.approx(100.0)

    def test_sell_filled_below_requested_is_positive_cost(self) -> None:
        # received 99 vs requested 100 → +100 bps of cost
        m = compute_daily_book_metrics(prev_equity=1.0, end_equity=1.0, trades=[_sell(fill=99.0, requested=100.0)])
        assert m.slippage_bps == pytest.approx(100.0)

    def test_none_when_no_trade_carries_a_requested_price(self) -> None:
        m = compute_daily_book_metrics(
            prev_equity=1.0,
            end_equity=1.0,
            trades=[_buy(requested=None)],  # type: ignore[arg-type]
        )
        assert m.slippage_bps is None


class TestClosingTradeStats:
    def test_hit_rate_and_expectancy_over_closing_trades(self) -> None:
        # Two winners (+30, +10) and one loser (-20) → hit_rate 2/3, expectancy +20/3.
        m = compute_daily_book_metrics(
            prev_equity=1000.0,
            end_equity=1000.0,
            trades=[_sell(pnl=30.0), _sell(pnl=-20.0), _sell(pnl=10.0)],
        )
        assert m.hit_rate == pytest.approx(2 / 3)
        assert m.expectancy == pytest.approx(20.0 / 3)

    def test_opening_only_day_is_none_not_zero(self) -> None:
        # Buys realize nothing (delta None), so a no-close day must not read as 0% hit rate.
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[_buy(), _buy()])
        assert m.hit_rate is None
        assert m.expectancy is None

    def test_break_even_close_is_not_a_win(self) -> None:
        m = compute_daily_book_metrics(prev_equity=1.0, end_equity=1.0, trades=[_sell(pnl=0.0), _sell(pnl=5.0)])
        assert m.hit_rate == pytest.approx(0.5)  # only the +5 counts as a win

    def test_only_closing_trades_count_toward_hit_rate(self) -> None:
        # A buy (opening) alongside a winning sell → hit_rate is over the one close.
        m = compute_daily_book_metrics(prev_equity=1.0, end_equity=1.0, trades=[_buy(), _sell(pnl=7.0)])
        assert m.hit_rate == pytest.approx(1.0)
        assert m.expectancy == pytest.approx(7.0)


class TestUnavailableColumns:
    def test_columns_without_a_data_source_stay_none(self) -> None:
        # These still require intraday equity / a return series — neither stored.
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[_buy()])
        assert m.drawdown_pct is None
        assert m.risk_adjusted_score is None
