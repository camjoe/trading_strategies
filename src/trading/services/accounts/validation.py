from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from common.coercion import (
    coerce_float,
    expect_float,
    expect_int,
    row_float,
    row_int,
    row_str,
)
from trading.domain.auto_trading.sizing import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.domain.exceptions import ValidationError
from trading.models.accounts import AccountConfig
from trading.models.books import BookSettingsUpdate

RISK_POLICIES = {"none", "fixed_stop", "take_profit", "stop_and_target"}
INSTRUMENT_MODES = {"equity", "leaps"}
OPTION_TYPES = {"call", "put", "both"}

_ENUM_FIELDS = {
    "risk_policy": RISK_POLICIES,
    "instrument_mode": INSTRUMENT_MODES,
    "option_type": OPTION_TYPES,
}


def normalize_lower(value: str) -> str:
    return value.strip().lower()


def validate_enum_value(value: str, field_name: str) -> str:
    normalized = normalize_lower(value)
    allowed = _ENUM_FIELDS[field_name]
    if normalized not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValidationError(f"{field_name} must be one of: {options}")
    return normalized


def normalize_risk_policy(risk_policy: str) -> str:
    return validate_enum_value(risk_policy, "risk_policy")


def normalize_instrument_mode(instrument_mode: str) -> str:
    return validate_enum_value(instrument_mode, "instrument_mode")


def normalize_option_type(option_type: str) -> str:
    return validate_enum_value(option_type, "option_type")


def validate_goal_return_range(goal_min_return_pct: float | None, goal_max_return_pct: float | None) -> None:
    if goal_min_return_pct is not None and goal_max_return_pct is not None:
        if goal_min_return_pct > goal_max_return_pct:
            raise ValidationError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def validate_range(
    min_val: object | None,
    max_val: object | None,
    field_prefix: str,
    min_name: str | None = None,
    max_name: str | None = None,
) -> None:
    if min_val is None or max_val is None:
        return
    min_name = min_name or f"{field_prefix}_min"
    max_name = max_name or f"{field_prefix}_max"
    min_num = coerce_float(min_val)
    max_num = coerce_float(max_val)
    if min_num is None or max_num is None:
        raise ValidationError(f"{field_prefix} range values must be numeric.")
    if min_num > max_num:
        raise ValidationError(f"{min_name} cannot be greater than {max_name}.")


def validate_or_none_range(value: object | None, min_bound: float, max_bound: float, field_name: str) -> None:
    if value is None:
        return
    numeric_value = coerce_float(value)
    if numeric_value is None:
        raise ValidationError(f"{field_name} must be numeric.")
    if (min_bound, max_bound) in [(0.0, 1.0), (0.0, 100.0)]:
        if not (min_bound <= numeric_value <= max_bound):
            raise ValidationError(f"{field_name} must be between {int(min_bound)} and {int(max_bound)}.")
    else:
        if numeric_value < min_bound:
            raise ValidationError(f"{field_name} must be >= {int(min_bound)}.")
        if numeric_value > max_bound:
            raise ValidationError(f"{field_name} must be <= {int(max_bound)}.")


def validate_option_settings(
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
) -> None:
    if option_type is not None and option_type not in OPTION_TYPES:
        raise ValidationError("option_type must be one of: call, put, both")
    validate_or_none_range(target_delta_min, 0, 1, "target_delta_min")
    validate_or_none_range(target_delta_max, 0, 1, "target_delta_max")
    validate_range(target_delta_min, target_delta_max, "target_delta")
    validate_or_none_range(option_min_dte, 0, 9999, "option_min_dte")
    validate_or_none_range(option_max_dte, 0, 9999, "option_max_dte")
    validate_range(option_min_dte, option_max_dte, "option", "option_min_dte", "option_max_dte")
    validate_or_none_range(iv_rank_min, 0, 100, "iv_rank_min")
    validate_or_none_range(iv_rank_max, 0, 100, "iv_rank_max")
    validate_range(iv_rank_min, iv_rank_max, "iv_rank")


def validate_position_sizing(
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> None:
    for field_name, value in (
        ("trade_size_pct", trade_size_pct),
        ("max_position_pct", max_position_pct),
    ):
        if value is None:
            continue
        numeric_value = coerce_float(value)
        if numeric_value is None:
            raise ValidationError(f"{field_name} must be numeric.")
        if numeric_value <= 0 or numeric_value > 100:
            raise ValidationError(f"{field_name} must be greater than 0 and <= 100.")
    has_position_sizing_inputs = trade_size_pct is not None and max_position_pct is not None
    if has_position_sizing_inputs:
        assert trade_size_pct is not None
        assert max_position_pct is not None
        trade_size_exceeds_position_limit = trade_size_pct > max_position_pct
        if trade_size_exceeds_position_limit:
            raise ValidationError("trade_size_pct cannot be greater than max_position_pct.")


def validate_position_sizing_from_inputs(
    current_trade_size_pct: float | None,
    current_max_position_pct: float | None,
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> tuple[float, float]:
    """Validate sizing inputs merged over the current (book-owned) values."""
    resolved_trade_size_pct = (
        trade_size_pct
        if trade_size_pct is not None
        else (current_trade_size_pct if current_trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT)
    )
    resolved_max_position_pct = (
        max_position_pct
        if max_position_pct is not None
        else (current_max_position_pct if current_max_position_pct is not None else DEFAULT_MAX_POSITION_PCT)
    )
    validate_position_sizing(resolved_trade_size_pct, resolved_max_position_pct)
    return resolved_trade_size_pct, resolved_max_position_pct


def resolved_float(value: float | None, row: "Mapping[str, object]", column: str) -> float | None:
    if value is not None:
        return value
    return row_float(row, column)


def resolved_int(value: int | None, row: "Mapping[str, object]", column: str) -> int | None:
    if value is not None:
        return value
    return row_int(row, column)


def validate_goal_range_from_inputs(
    current: "Mapping[str, object]",
    goal_min_return_pct: float | None,
    goal_max_return_pct: float | None,
) -> None:
    """Validate goal inputs merged over the current (book-owned) values."""
    min_value = resolved_float(goal_min_return_pct, current, "goal_min_return_pct")
    max_value = resolved_float(goal_max_return_pct, current, "goal_max_return_pct")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValidationError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def validate_option_settings_from_inputs(
    current: "Mapping[str, object]",
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
) -> None:
    min_dte = resolved_int(option_min_dte, current, "option_min_dte")
    max_dte = resolved_int(option_max_dte, current, "option_max_dte")
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise ValidationError("option_min_dte cannot be greater than option_max_dte.")
    delta_min = resolved_float(target_delta_min, current, "target_delta_min")
    delta_max = resolved_float(target_delta_max, current, "target_delta_max")
    iv_min = resolved_float(iv_rank_min, current, "iv_rank_min")
    iv_max = resolved_float(iv_rank_max, current, "iv_rank_max")
    resolved_opt_type = option_type if option_type is not None else row_str(current, "option_type")
    validate_option_settings(
        resolved_opt_type,
        delta_min,
        delta_max,
        min_dte,
        max_dte,
        iv_min,
        iv_max,
    )


# Each writable book column paired with the coercion or normalization applied to
# its AccountConfig field. One table so the create, account-update, and
# explicit-book-edit paths share a single column list and cannot drift into
# different coercion per site. ``max_trades_per_run`` is the one book settings
# column absent from AccountConfig; its editor overlays it separately.
_BOOK_COLUMN_COERCERS: dict[str, Callable[..., object]] = {
    "learning_enabled": expect_int,
    "risk_policy": normalize_risk_policy,
    "instrument_mode": normalize_instrument_mode,
    "option_type": normalize_option_type,
    "goal_period": normalize_lower,
    "stop_loss_pct": expect_float,
    "take_profit_pct": expect_float,
    "trade_size_pct": expect_float,
    "max_position_pct": expect_float,
    "goal_min_return_pct": expect_float,
    "goal_max_return_pct": expect_float,
    "option_profit_take_pct": expect_float,
    "option_max_loss_pct": expect_float,
    "option_strike_offset_pct": expect_float,
    "option_min_dte": expect_int,
    "option_max_dte": expect_int,
    "target_delta_min": expect_float,
    "target_delta_max": expect_float,
    "max_premium_per_trade": expect_float,
    "max_contracts_per_trade": expect_int,
    "iv_rank_min": expect_float,
    "iv_rank_max": expect_float,
    "roll_dte_threshold": expect_int,
}


def book_settings_update_from_config(config: AccountConfig) -> BookSettingsUpdate:
    """Coerce a partial AccountConfig into a typed book-settings update.

    Only the fields the caller set (non-None) are carried; each passes through
    its column's normalizer or coercer.
    """
    kwargs: dict[str, Any] = {}
    for column, coerce in _BOOK_COLUMN_COERCERS.items():
        raw = getattr(config, column)
        if raw is not None:
            kwargs[column] = coerce(raw)
    return BookSettingsUpdate(**kwargs)
