import math

import pytest
from hypothesis import given, settings, strategies as st

from trading.domain.returns import safe_return_pct, total_return_pct


class TestTotalReturnPct:
    def test_matches_first_last_equity(self) -> None:
        assert total_return_pct(first_equity=10_000.0, last_equity=11_000.0) == pytest.approx(10.0)
        assert total_return_pct(first_equity=10_000.0, last_equity=9_500.0) == pytest.approx(-5.0)

    def test_zero_first_equity_raises(self) -> None:
        # The strict half of the pair: an interval starting at zero equity has no
        # return, and a caller that cannot rule that out wants safe_return_pct.
        with pytest.raises(ValueError, match="first_equity is 0"):
            total_return_pct(first_equity=0.0, last_equity=100.0)


class TestSafeReturnPct:
    def test_none_start_returns_none(self):
        assert safe_return_pct(None, 110.0) is None

    def test_none_end_returns_none(self):
        assert safe_return_pct(100.0, None) is None

    def test_zero_start_returns_none(self):
        assert safe_return_pct(0.0, 110.0) is None

    def test_negative_start_returns_none(self):
        assert safe_return_pct(-10.0, 110.0) is None

    def test_positive_gain(self):
        result = safe_return_pct(100.0, 110.0)
        assert result == pytest.approx(10.0)

    def test_positive_loss(self):
        result = safe_return_pct(100.0, 90.0)
        assert result == pytest.approx(-10.0)

    def test_no_change_returns_zero(self):
        result = safe_return_pct(100.0, 100.0)
        assert result == pytest.approx(0.0)


class TestSafeReturnPctNaNAndInfGuards:
    """Guard tests: NaN and inf inputs must not silently produce non-None garbage."""

    def test_nan_start_returns_none(self) -> None:
        # float("nan") <= 0 is False, so nan silently passes the existing guard
        # without the math.isfinite check — this pinpoints the regression risk.
        assert safe_return_pct(float("nan"), 110.0) is None

    def test_nan_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("nan")) is None

    def test_pos_inf_start_returns_none(self) -> None:
        # +inf > 0, so the <= 0 guard does not catch it without isfinite.
        assert safe_return_pct(float("inf"), 110.0) is None

    def test_neg_inf_start_returns_none(self) -> None:
        # -inf is already caught by <= 0, but isfinite provides defence-in-depth.
        assert safe_return_pct(float("-inf"), 110.0) is None

    def test_pos_inf_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("inf")) is None

    def test_neg_inf_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("-inf")) is None

    @settings(max_examples=60, deadline=None)
    @given(
        start=st.floats(min_value=1.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
        end=st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    )
    def test_hypothesis_valid_inputs_return_finite_result(self, start: float, end: float) -> None:
        result = safe_return_pct(start, end)
        assert result is not None
        assert isinstance(result, float)
        assert math.isfinite(result)
