from __future__ import annotations

import pytest

from trading.domain.daily_metrics import DailyTrade, compute_daily_book_metrics


def _buy(qty=10.0, fill=100.0, requested=100.0, commission=0.0) -> DailyTrade:
    return DailyTrade(
        side="buy", filled_qty=qty, avg_fill_price=fill, requested_price=requested, commission=commission
    )


def _sell(qty=10.0, fill=100.0, requested=100.0, commission=0.0) -> DailyTrade:
    return DailyTrade(
        side="sell", filled_qty=qty, avg_fill_price=fill, requested_price=requested, commission=commission
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


class TestUnavailableColumns:
    def test_columns_without_a_data_source_stay_none(self) -> None:
        # These require intraday equity / per-trade P&L / a return series — none stored.
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[_buy()])
        assert m.drawdown_pct is None
        assert m.hit_rate is None
        assert m.expectancy is None
        assert m.risk_adjusted_score is None
