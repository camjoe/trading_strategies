import pytest

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
