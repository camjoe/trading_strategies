"""Compounded OOS aggregation (pure domain math): compounding, gap detection,
and the period-return helper."""

from __future__ import annotations

from datetime import date

import pytest

from backtesting.domain.optimization.aggregation import compound_oos_returns, period_return_pct
from backtesting.optimizer_models import OOSReturnSegment


def _segment(index: int, start: date, end: date, ret: float) -> OOSReturnSegment:
    return OOSReturnSegment(window_index=index, test_start=start, test_end=end, return_pct=ret)


def test_period_return_pct_matches_first_last_equity() -> None:
    assert period_return_pct(first_equity=10_000.0, last_equity=11_000.0) == pytest.approx(10.0)
    assert period_return_pct(first_equity=10_000.0, last_equity=9_500.0) == pytest.approx(-5.0)


class TestCompound:
    def test_compounds_returns_not_sums(self) -> None:
        # Two contiguous +10% windows compound to 21%, not 20%.
        series = compound_oos_returns(
            [
                _segment(1, date(2023, 1, 1), date(2023, 1, 31), 10.0),
                _segment(2, date(2023, 2, 1), date(2023, 2, 28), 10.0),
            ]
        )
        assert series.compounded_return_pct == pytest.approx(21.0)
        assert [p.cumulative_return_pct for p in series.points] == pytest.approx([10.0, 21.0])
        assert not series.has_gaps
        assert all(not p.gap_before for p in series.points)

    def test_negative_windows_compound_down(self) -> None:
        series = compound_oos_returns(
            [
                _segment(1, date(2023, 1, 1), date(2023, 1, 31), -10.0),
                _segment(2, date(2023, 2, 1), date(2023, 2, 28), -10.0),
            ]
        )
        # 0.9 * 0.9 - 1 = -19%
        assert series.compounded_return_pct == pytest.approx(-19.0)

    def test_flags_gap_when_windows_not_contiguous(self) -> None:
        # A March window following a January window (step > test) leaves a gap.
        series = compound_oos_returns(
            [
                _segment(1, date(2023, 1, 1), date(2023, 1, 31), 5.0),
                _segment(2, date(2023, 3, 1), date(2023, 3, 31), 5.0),
            ]
        )
        assert series.has_gaps
        assert series.points[0].gap_before is False  # first window never has a gap before it
        assert series.points[1].gap_before is True

    def test_contiguous_next_day_is_not_a_gap(self) -> None:
        series = compound_oos_returns(
            [
                _segment(1, date(2023, 1, 1), date(2023, 1, 31), 1.0),
                _segment(2, date(2023, 2, 1), date(2023, 2, 28), 1.0),
            ]
        )
        assert not series.has_gaps

    def test_single_window_series(self) -> None:
        series = compound_oos_returns([_segment(1, date(2023, 1, 1), date(2023, 1, 31), 3.5)])
        assert series.compounded_return_pct == pytest.approx(3.5)
        assert len(series.points) == 1
        assert not series.has_gaps

    def test_empty_series(self) -> None:
        series = compound_oos_returns([])
        assert series.points == []
        assert series.compounded_return_pct == pytest.approx(0.0)
        assert not series.has_gaps
