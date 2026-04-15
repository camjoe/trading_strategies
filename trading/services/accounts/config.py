from __future__ import annotations

from collections.abc import Callable

from trading.domain.auto_trader_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.utils.coercion import (
    coerce_float,
    coerce_str,
    row_float,
    row_int,
    row_str,
    to_float_obj,
    to_int_obj,
)

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


def normalize_lower_obj(value: object) -> object:
    text = coerce_str(value)
    if text is None:
        raise ValueError("Expected non-null string value")
    return normalize_lower(text)


def validate_enum_value(value: str, field_name: str) -> str:
    normalized = normalize_lower(value)
    allowed = _ENUM_FIELDS[field_name]
    if normalized not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {options}")
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
            raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


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
        raise ValueError(f"{field_prefix} range values must be numeric.")
    if min_num > max_num:
        raise ValueError(f"{min_name} cannot be greater than {max_name}.")


def validate_or_none_range(value: object | None, min_bound: float, max_bound: float, field_name: str) -> None:
    if value is None:
        return
    numeric_value = coerce_float(value)
    if numeric_value is None:
        raise ValueError(f"{field_name} must be numeric.")
    if (min_bound, max_bound) in [(0.0, 1.0), (0.0, 100.0)]:
        if not (min_bound <= numeric_value <= max_bound):
            raise ValueError(f"{field_name} must be between {int(min_bound)} and {int(max_bound)}.")
    else:
        if numeric_value < min_bound:
            raise ValueError(f"{field_name} must be >= {int(min_bound)}.")
        if numeric_value > max_bound:
            raise ValueError(f"{field_name} must be <= {int(max_bound)}.")


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
        raise ValueError("option_type must be one of: call, put, both")
    validate_or_none_range(target_delta_min, 0, 1, "target_delta_min")
    validate_or_none_range(target_delta_max, 0, 1, "target_delta_max")
    validate_range(target_delta_min, target_delta_max, "target_delta")
    validate_or_none_range(option_min_dte, 0, 9999, "option_min_dte")
    validate_or_none_range(option_max_dte, 0, 9999, "option_max_dte")
    validate_range(option_min_dte, option_max_dte, "option", "option_min_dte", "option_max_dte")
    validate_or_none_range(iv_rank_min, 0, 100, "iv_rank_min")
    validate_or_none_range(iv_rank_max, 0, 100, "iv_rank_max")
    validate_range(iv_rank_min, iv_rank_max, "iv_rank")


def resolve_sizing_value(
    value: float | None,
    row: dict[str, object],
    column: str,
    default: float,
) -> float:
    if value is not None:
        return value
    existing = row_float(row, column)
    if existing is not None:
        return existing
    return default


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
            raise ValueError(f"{field_name} must be numeric.")
        if numeric_value <= 0 or numeric_value > 100:
            raise ValueError(f"{field_name} must be greater than 0 and <= 100.")
    if trade_size_pct is not None and max_position_pct is not None and trade_size_pct > max_position_pct:
        raise ValueError("trade_size_pct cannot be greater than max_position_pct.")


def validate_position_sizing_from_inputs(
    account: dict[str, object],
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> tuple[float, float]:
    resolved_trade_size_pct = resolve_sizing_value(
        trade_size_pct,
        account,
        "trade_size_pct",
        DEFAULT_TRADE_SIZE_PCT,
    )
    resolved_max_position_pct = resolve_sizing_value(
        max_position_pct,
        account,
        "max_position_pct",
        DEFAULT_MAX_POSITION_PCT,
    )
    validate_position_sizing(resolved_trade_size_pct, resolved_max_position_pct)
    return resolved_trade_size_pct, resolved_max_position_pct


def append_update(
    updates: list[str],
    params: list[object],
    column: str,
    value: object | None,
    transform: Callable[[object], object] | None = None,
) -> None:
    if value is None:
        return
    updates.append(f"{column} = ?")
    params.append(transform(value) if transform is not None else value)


def append_numeric_updates(
    updates: list[str],
    params: list[object],
    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]],
) -> None:
    for column, value, transform in numeric_fields:
        append_update(updates, params, column, value, transform)


def resolved_float(value: float | None, row: dict[str, object], column: str) -> float | None:
    if value is not None:
        return value
    return row_float(row, column)


def resolved_int(value: int | None, row: dict[str, object], column: str) -> int | None:
    if value is not None:
        return value
    return row_int(row, column)


def validate_goal_range_from_inputs(
    account: dict[str, object],
    goal_min_return_pct: float | None,
    goal_max_return_pct: float | None,
) -> None:
    min_value = resolved_float(goal_min_return_pct, account, "goal_min_return_pct")
    max_value = resolved_float(goal_max_return_pct, account, "goal_max_return_pct")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def validate_option_settings_from_inputs(
    account: dict[str, object],
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
) -> None:
    min_dte = resolved_int(option_min_dte, account, "option_min_dte")
    max_dte = resolved_int(option_max_dte, account, "option_max_dte")
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    delta_min = resolved_float(target_delta_min, account, "target_delta_min")
    delta_max = resolved_float(target_delta_max, account, "target_delta_max")
    iv_min = resolved_float(iv_rank_min, account, "iv_rank_min")
    iv_max = resolved_float(iv_rank_max, account, "iv_rank_max")
    resolved_opt_type = option_type if option_type is not None else row_str(account, "option_type")
    validate_option_settings(
        resolved_opt_type,
        delta_min,
        delta_max,
        min_dte,
        max_dte,
        iv_min,
        iv_max,
    )
