import sqlite3

import pytest

from trading.services.reporting_service import (
    alpha_pct,
    benchmark_available,
    compute_market_value_and_unrealized,
    infer_overall_trend,
    positions_summary_text,
    strategy_return_pct,
)


class TestComputeMarketValueAndUnrealized:
    def test_single_position_with_price(self) -> None:
        mv, unrealized = compute_market_value_and_unrealized(
            positions={"AAPL": 10.0},
            avg_cost={"AAPL": 150.0},
            prices={"AAPL": 160.0},
        )
        assert mv == pytest.approx(1600.0)
        assert unrealized == pytest.approx(100.0)

    def test_position_missing_price_is_skipped(self) -> None:
        mv, unrealized = compute_market_value_and_unrealized(
            positions={"AAPL": 10.0, "MSFT": 5.0},
            avg_cost={"AAPL": 100.0, "MSFT": 200.0},
            prices={"AAPL": 120.0},
        )
        assert mv == pytest.approx(1200.0)
        assert unrealized == pytest.approx(200.0)

    def test_empty_positions_returns_zeros(self) -> None:
        mv, unrealized = compute_market_value_and_unrealized({}, {}, {})
        assert mv == 0.0
        assert unrealized == 0.0

    def test_unrealized_loss(self) -> None:
        _, unrealized = compute_market_value_and_unrealized(
            positions={"SPY": 2.0},
            avg_cost={"SPY": 500.0},
            prices={"SPY": 480.0},
        )
        assert unrealized == pytest.approx(-40.0)


class TestStrategyReturnPct:
    def test_gain(self) -> None:
        assert strategy_return_pct(110.0, 100.0) == pytest.approx(10.0)

    def test_loss(self) -> None:
        assert strategy_return_pct(90.0, 100.0) == pytest.approx(-10.0)

    def test_no_change(self) -> None:
        assert strategy_return_pct(100.0, 100.0) == pytest.approx(0.0)

    def test_zero_initial_cash_raises(self) -> None:
        with pytest.raises(ValueError):
            strategy_return_pct(100.0, 0.0)


class TestBenchmarkAvailable:
    def test_both_present_returns_true(self) -> None:
        assert benchmark_available(105.0, 5.0) is True

    def test_equity_none_returns_false(self) -> None:
        assert benchmark_available(None, 5.0) is False

    def test_return_none_returns_false(self) -> None:
        assert benchmark_available(105.0, None) is False

    def test_both_none_returns_false(self) -> None:
        assert benchmark_available(None, None) is False


class TestAlphaPct:
    def test_positive_alpha(self) -> None:
        assert alpha_pct(12.0, 8.0) == pytest.approx(4.0)

    def test_negative_alpha(self) -> None:
        assert alpha_pct(5.0, 10.0) == pytest.approx(-5.0)

    def test_zero_alpha(self) -> None:
        assert alpha_pct(7.0, 7.0) == pytest.approx(0.0)


class TestPositionsSummaryText:
    def test_empty_positions(self) -> None:
        count, text = positions_summary_text({})
        assert count == 0
        assert text == "none"

    def test_few_positions_sorted(self) -> None:
        count, text = positions_summary_text({"MSFT": 2.0, "AAPL": 5.0})
        assert count == 2
        assert text.startswith("AAPL")

    def test_more_than_five_truncated(self) -> None:
        positions = {f"T{i}": float(i) for i in range(7)}
        count, text = positions_summary_text(positions)
        assert count == 7
        assert text.endswith(", ...")

    def test_exactly_five_no_ellipsis(self) -> None:
        positions = {f"T{i}": float(i) for i in range(5)}
        _, text = positions_summary_text(positions)
        assert "..." not in text


class TestInferOverallTrend:
    def _make_row(self, equity: float) -> sqlite3.Row:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE t (equity REAL)")
        conn.execute("INSERT INTO t VALUES (?)", [equity])
        return conn.execute("SELECT * FROM t").fetchone()

    def _run(
        self,
        history_equities: list[float],
        current_equity: float,
        lookback: int = 10,
    ) -> str:
        rows = [self._make_row(e) for e in history_equities]

        def fake_fetch(conn, *, account_id, limit):
            return rows

        def fake_row_float(row, key):
            return float(row[key])

        return infer_overall_trend(
            None,  # type: ignore[arg-type]
            account_id=1,
            current_equity=current_equity,
            lookback=lookback,
            fetch_recent_equity_rows_fn=fake_fetch,
            row_float_fn=fake_row_float,
        )

    def test_uptrend(self) -> None:
        # history + current gives a >1% gain
        assert self._run([90.0, 95.0], 110.0) == "up"

    def test_downtrend(self) -> None:
        assert self._run([110.0, 105.0], 90.0) == "down"

    def test_flat(self) -> None:
        assert self._run([100.0, 100.0], 100.5) == "flat"

    def test_insufficient_data_fewer_than_three_points(self) -> None:
        # Only one history point + current = 2 points total → insufficient
        assert self._run([100.0], 105.0) == "insufficient-data"

    def test_insufficient_data_zero_first_equity(self) -> None:
        # Rows returned newest-first; after reverse oldest is first.
        # Pass [50.0, 0.0] so oldest (first after reverse) == 0.0.
        assert self._run([50.0, 0.0], 80.0) == "insufficient-data"
