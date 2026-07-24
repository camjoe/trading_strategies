from __future__ import annotations

import pytest

from common.constants import ANNUALIZATION_FACTOR
from trading.domain.daily_metrics import (
    RISK_ADJUSTED_MIN_SESSIONS,
    DailyTrade,
    compute_daily_book_metrics,
)


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
    def test_drawdown_stays_none_without_intraday_equity(self) -> None:
        # drawdown_pct needs intraday equity, which is not stored at this grain.
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[_buy()])
        assert m.drawdown_pct is None


class TestRiskAdjustedScore:
    def _priors(self, *values: float) -> list[float]:
        return list(values)

    def test_none_without_enough_history(self) -> None:
        # Today's return plus two priors is 3 sessions — below the minimum sample.
        m = compute_daily_book_metrics(
            prev_equity=1000.0, end_equity=1010.0, trades=[], prior_returns=self._priors(2.0, -1.0)
        )
        assert m.risk_adjusted_score is None

    def test_none_when_no_prior_returns_supplied(self) -> None:
        # The writer omits priors on a book's early days; one point is not a series.
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[])
        assert m.risk_adjusted_score is None

    def test_zero_dispersion_is_none(self) -> None:
        # A genuinely flat return series (a book whose equity doesn't move) has
        # zero volatility → Sharpe is undefined, not 0.
        priors = self._priors(*([0.0] * (RISK_ADJUSTED_MIN_SESSIONS - 1)))
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1000.0, trades=[], prior_returns=priors)
        assert m.return_pct == pytest.approx(0.0)  # today is also flat → all equal
        assert m.risk_adjusted_score is None

    def test_zero_mean_series_scores_zero(self) -> None:
        # Five +1% and five -1% returns → mean 0 → Sharpe 0.0 (dispersion is nonzero).
        priors = self._priors(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0)  # 9 priors
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1010.0, trades=[], prior_returns=priors)
        assert m.risk_adjusted_score == pytest.approx(0.0)

    def test_annualized_sharpe_matches_convention(self) -> None:
        # Window of five 2.0 and five 0.0 → mean 1.0, population std 1.0 →
        # Sharpe == 1.0 / 1.0 * ANNUALIZATION_FACTOR.
        priors = self._priors(2.0, 2.0, 2.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # 9 priors
        m = compute_daily_book_metrics(prev_equity=1000.0, end_equity=1020.0, trades=[], prior_returns=priors)
        assert m.return_pct == pytest.approx(2.0)  # today is +2.0, the tenth value
        assert m.risk_adjusted_score == pytest.approx(ANNUALIZATION_FACTOR)

    def test_window_caps_to_recent_sessions(self) -> None:
        # Priors beyond the trailing window are dropped: only the most recent
        # RISK_ADJUSTED_WINDOW_SESSIONS - 1 (plus today) count. An old, wild value
        # far past the cap must not move the score off the recent flat run — if it
        # leaked in, the huge dispersion would produce a (non-None) score.
        recent_flat = [0.0] * 30  # far more than the window; today is flat too
        old_outlier = [999.0]
        m = compute_daily_book_metrics(
            prev_equity=1000.0, end_equity=1000.0, trades=[], prior_returns=recent_flat + old_outlier
        )
        assert m.risk_adjusted_score is None  # recent window is flat → zero dispersion
