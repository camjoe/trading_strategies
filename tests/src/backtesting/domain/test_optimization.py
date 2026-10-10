"""Walk-forward optimization domain math: grid search, fingerprinting, the
calmar_v1 objective, and compounded out-of-sample aggregation."""

from __future__ import annotations

from datetime import date

import pytest

from backtesting.domain.optimization import (
    MAX_DRAWDOWN_ELIGIBILITY_PCT,
    MIN_CANDIDATE_TRADES,
    compound_oos_returns,
    evaluate_candidate,
    generate_candidates,
    params_fingerprint,
    select_winner,
)
from backtesting.models.optimizer import OOSReturnSegment
from trading.domain.exceptions import ValidationError


def _segment(index: int, start: date, end: date, ret: float) -> OOSReturnSegment:
    return OOSReturnSegment(window_index=index, test_start=start, test_end=end, return_pct=ret)


class TestGridSearch:
    def test_generates_canonical_ordered_product(self) -> None:
        candidates = generate_candidates({"fast_window": [5, 10], "slow_window": [20, 30]}, budget=256)
        assert candidates == [
            {"fast_window": 5, "slow_window": 20},
            {"fast_window": 5, "slow_window": 30},
            {"fast_window": 10, "slow_window": 20},
            {"fast_window": 10, "slow_window": 30},
        ]

    def test_rejects_grid_over_budget(self) -> None:
        with pytest.raises(ValidationError, match="exceeds candidate budget"):
            generate_candidates({"a": [1, 2, 3], "b": [1, 2, 3]}, budget=8)

    def test_rejects_empty_space_and_empty_values(self) -> None:
        with pytest.raises(ValidationError):
            generate_candidates({}, budget=8)
        with pytest.raises(ValidationError):
            generate_candidates({"a": []}, budget=8)


class TestParamsFingerprint:
    def test_hash_is_key_order_independent(self) -> None:
        # Equal parameter sets collide regardless of insertion order — the basis for
        # the one-candidate-per-window uniqueness constraint on trials.
        assert params_fingerprint({"fast_window": 5, "slow_window": 20}) == params_fingerprint(
            {"slow_window": 20, "fast_window": 5}
        )

    def test_different_params_hash_differently(self) -> None:
        assert params_fingerprint({"slow_window": 20}) != params_fingerprint({"slow_window": 40})


class TestObjective:
    def test_calmar_v1_floor_keeps_low_drawdown_finite(self) -> None:
        # Drawdown magnitude below the 1pp floor uses the floor as denominator, so a
        # near-zero-drawdown candidate is still scored instead of dropping out.
        result = evaluate_candidate(
            index=0, params={}, annualized_return_pct=10.0, max_drawdown_pct=-0.2, trade_count=10
        )
        assert result.score == 10.0

    def test_rejects_too_few_trades(self) -> None:
        result = evaluate_candidate(
            index=0,
            params={"x": 1},
            annualized_return_pct=20.0,
            max_drawdown_pct=-5.0,
            trade_count=MIN_CANDIDATE_TRADES - 1,
        )
        assert not result.eligible
        assert result.score is None
        assert "too_few_trades" in result.rejection_reason

    def test_negative_return_is_eligible_but_scored_low(self) -> None:
        # The positive-return training gate was intentionally dropped: a down-regime
        # candidate stays selectable (best-of-field) and its OOS/holdout run is the judge.
        result = evaluate_candidate(
            index=0, params={}, annualized_return_pct=-8.0, max_drawdown_pct=-5.0, trade_count=10
        )
        assert result.eligible
        assert result.score is not None and result.score < 0

    def test_rejects_missing_return_and_excess_drawdown(self) -> None:
        missing = evaluate_candidate(
            index=0, params={}, annualized_return_pct=None, max_drawdown_pct=-5.0, trade_count=10
        )
        assert missing.rejection_reason == "no_annualized_return"
        deep = evaluate_candidate(
            index=1,
            params={},
            annualized_return_pct=10.0,
            max_drawdown_pct=MAX_DRAWDOWN_ELIGIBILITY_PCT - 1.0,
            trade_count=10,
        )
        assert "drawdown_exceeds_limit" in deep.rejection_reason

    def test_select_winner_ranks_by_score_then_tiebreaks(self) -> None:
        results = [
            evaluate_candidate(
                index=0, params={"n": 0}, annualized_return_pct=8.0, max_drawdown_pct=-12.0, trade_count=8
            ),
            evaluate_candidate(
                index=1, params={"n": 1}, annualized_return_pct=30.0, max_drawdown_pct=-5.0, trade_count=12
            ),
            evaluate_candidate(
                index=2, params={"n": 2}, annualized_return_pct=8.0, max_drawdown_pct=-12.0, trade_count=8
            ),
        ]
        assert select_winner(results).params == {"n": 1}

    def test_select_winner_raises_when_none_eligible(self) -> None:
        # Ineligible via a still-active gate (too few trades); the error names the reason.
        results = [
            evaluate_candidate(index=0, params={}, annualized_return_pct=5.0, max_drawdown_pct=-5.0, trade_count=1),
        ]
        with pytest.raises(ValidationError, match="No eligible candidate.*too_few_trades"):
            select_winner(results)


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
