from __future__ import annotations

import pytest

from trading.domain.strategies.parameter_validation import validate_params_against_primitive


def test_accepts_and_coerces_known_knobs_from_strings() -> None:
    out = validate_params_against_primitive("trend", {"fast_window": "15", "slow_window": 40})

    assert out == {"fast_window": 15, "slow_window": 40}


def test_coerces_float_knob() -> None:
    out = validate_params_against_primitive("mean_reversion", {"band_pct": "0.05"})

    assert out == {"band_pct": 0.05}


def test_empty_params_is_valid() -> None:
    assert validate_params_against_primitive("trend", {}) == {}


def test_rejects_unknown_knob_name() -> None:
    with pytest.raises(ValueError, match="Unknown knob"):
        validate_params_against_primitive("trend", {"not_a_knob": 1})


def test_rejects_non_numeric_for_int_knob() -> None:
    with pytest.raises(ValueError, match="integer"):
        validate_params_against_primitive("trend", {"fast_window": "abc"})


def test_rejects_fractional_value_for_int_knob() -> None:
    with pytest.raises(ValueError, match="integer"):
        validate_params_against_primitive("trend", {"fast_window": 5.5})


def test_unknown_primitive_raises() -> None:
    with pytest.raises(ValueError, match="Unknown signal primitive"):
        validate_params_against_primitive("not_a_primitive", {})
