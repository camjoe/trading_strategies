import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from trading.domain.returns import safe_return_pct


def _coerce(v: object) -> float | None:
    if v is None:
        return None
    return float(v)


class TestSafeReturnPct:
    def test_none_start_returns_none(self):
        assert safe_return_pct(None, 110.0, coerce_float_fn=_coerce) is None

    def test_none_end_returns_none(self):
        assert safe_return_pct(100.0, None, coerce_float_fn=_coerce) is None

    def test_zero_start_returns_none(self):
        assert safe_return_pct(0.0, 110.0, coerce_float_fn=_coerce) is None

    def test_negative_start_returns_none(self):
        assert safe_return_pct(-10.0, 110.0, coerce_float_fn=_coerce) is None

    def test_positive_gain(self):
        result = safe_return_pct(100.0, 110.0, coerce_float_fn=_coerce)
        assert result == pytest.approx(10.0)

    def test_positive_loss(self):
        result = safe_return_pct(100.0, 90.0, coerce_float_fn=_coerce)
        assert result == pytest.approx(-10.0)

    def test_no_change_returns_zero(self):
        result = safe_return_pct(100.0, 100.0, coerce_float_fn=_coerce)
        assert result == pytest.approx(0.0)

    def test_coerce_fn_is_called_on_both_inputs(self):
        calls: list[object] = []

        def tracking_coerce(v: object) -> float | None:
            calls.append(v)
            return float(v)  # type: ignore[arg-type]

        safe_return_pct(50.0, 75.0, coerce_float_fn=tracking_coerce)
        assert calls == [50.0, 75.0]


class TestSafeReturnPctNaNAndInfGuards:
    """Guard tests: NaN and inf inputs must not silently produce non-None garbage."""

    def test_nan_start_returns_none(self) -> None:
        # float("nan") <= 0 is False, so nan silently passes the existing guard
        # without the math.isfinite check — this pinpoints the regression risk.
        assert safe_return_pct(float("nan"), 110.0, coerce_float_fn=_coerce) is None

    def test_nan_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("nan"), coerce_float_fn=_coerce) is None

    def test_pos_inf_start_returns_none(self) -> None:
        # +inf > 0, so the <= 0 guard does not catch it without isfinite.
        assert safe_return_pct(float("inf"), 110.0, coerce_float_fn=_coerce) is None

    def test_neg_inf_start_returns_none(self) -> None:
        # -inf is already caught by <= 0, but isfinite provides defence-in-depth.
        assert safe_return_pct(float("-inf"), 110.0, coerce_float_fn=_coerce) is None

    def test_pos_inf_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("inf"), coerce_float_fn=_coerce) is None

    def test_neg_inf_end_returns_none(self) -> None:
        assert safe_return_pct(100.0, float("-inf"), coerce_float_fn=_coerce) is None

    @settings(max_examples=60, deadline=None)
    @given(
        start=st.floats(min_value=1.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
        end=st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
    )
    def test_hypothesis_valid_inputs_return_finite_result(
        self, start: float, end: float
    ) -> None:
        result = safe_return_pct(start, end, coerce_float_fn=_coerce)
        assert result is not None
        assert isinstance(result, float)
        assert math.isfinite(result)
