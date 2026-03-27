import sqlite3
from typing import Callable
from common.time import utc_now_iso
from trading.database.db_backend import DuplicateRecordError
from trading.coercion import coerce_str, row_float, row_int, row_str, to_float_obj, to_int_obj


RISK_POLICIES = {"none", "fixed_stop", "take_profit", "stop_and_target"}
INSTRUMENT_MODES = {"equity", "leaps"}
OPTION_TYPES = {"call", "put", "both"}

# Map field names to their valid enum sets for generic validation
_ENUM_FIELDS = {
    "risk_policy": RISK_POLICIES,
    "instrument_mode": INSTRUMENT_MODES,
    "option_type": OPTION_TYPES,
}


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


def _normalize_lower(value: str) -> str:
    return value.strip().lower()


def _normalize_lower_obj(value: object) -> object:
    text = coerce_str(value)
    if text is None:
        raise ValueError("Expected non-null string value")
    return _normalize_lower(text)


def _validate_enum_value(value: str, field_name: str) -> str:
    """Normalize and validate an enum string field against allowed values."""
    normalized = _normalize_lower(value)
    allowed = _ENUM_FIELDS[field_name]
    if normalized not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} must be one of: {options}")
    return normalized


def _normalize_risk_policy(risk_policy: str) -> str:
    return _validate_enum_value(risk_policy, "risk_policy")


def _normalize_instrument_mode(instrument_mode: str) -> str:
    return _validate_enum_value(instrument_mode, "instrument_mode")


def _normalize_option_type(option_type: str) -> str:
    return _validate_enum_value(option_type, "option_type")


def _validate_goal_return_range(goal_min_return_pct: float | None, goal_max_return_pct: float | None) -> None:
    if goal_min_return_pct is not None and goal_max_return_pct is not None:
        if goal_min_return_pct > goal_max_return_pct:
            raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def _validate_range(min_val: object | None, max_val: object | None, field_prefix: str, min_name: str = None, max_name: str = None) -> None:
    """Helper to validate that min <= max for a pair of numeric fields."""
    if min_val is None or max_val is None:
        return
    min_name = min_name or f"{field_prefix}_min"
    max_name = max_name or f"{field_prefix}_max"
    if float(min_val) > float(max_val):
        raise ValueError(f"{min_name} cannot be greater than {max_name}.")


def _validate_or_none_range(value: object | None, min_bound: float, max_bound: float, field_name: str) -> None:
    """Validate that a value (if present) falls within [min_bound, max_bound]."""
    if value is None:
        return
    v = float(value)
    # For fractional bounds (0-1, 0-100), use "between X and Y" format
    # For integer bounds like 0-9999, use single-sided checks
    if (min_bound, max_bound) in [(0.0, 1.0), (0.0, 100.0)]:
        if not (min_bound <= v <= max_bound):
            raise ValueError(f"{field_name} must be between {int(min_bound)} and {int(max_bound)}.")
    else:
        if v < min_bound:
            raise ValueError(f"{field_name} must be >= {int(min_bound)}.")
        if v > max_bound:
            raise ValueError(f"{field_name} must be <= {int(max_bound)}.")


def _validate_option_settings(
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
    _validate_or_none_range(target_delta_min, 0, 1, "target_delta_min")
    _validate_or_none_range(target_delta_max, 0, 1, "target_delta_max")
    _validate_range(target_delta_min, target_delta_max, "target_delta")
    _validate_or_none_range(option_min_dte, 0, 9999, "option_min_dte")
    _validate_or_none_range(option_max_dte, 0, 9999, "option_max_dte")
    _validate_range(option_min_dte, option_max_dte, "option", "option_min_dte", "option_max_dte")
    _validate_or_none_range(iv_rank_min, 0, 100, "iv_rank_min")
    _validate_or_none_range(iv_rank_max, 0, 100, "iv_rank_max")
    _validate_range(iv_rank_min, iv_rank_max, "iv_rank")


def _append_update(
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


def format_goal_text(row: sqlite3.Row) -> str:
    min_goal = row_float(row, "goal_min_return_pct")
    max_goal = row_float(row, "goal_max_return_pct")
    goal_period = row_str(row, "goal_period") or "period"
    if min_goal is None and max_goal is None:
        return "not-set"
    if min_goal is not None and max_goal is not None:
        return f"{min_goal:.2f}% to {max_goal:.2f}% per {goal_period}"
    if min_goal is not None:
        return f">= {min_goal:.2f}% per {goal_period}"
    return f"<= {max_goal:.2f}% per {goal_period}"


def _account_summary_line(row: sqlite3.Row) -> str:
    goal_text = format_goal_text(row)
    initial_cash = row_float(row, "initial_cash")
    learning_enabled = row_int(row, "learning_enabled")
    initial_cash_text = f"{initial_cash:.2f}" if initial_cash is not None else "n/a"
    return (
        f"[{row['id']}] {row['name']} ({row['descriptive_name']}) | strategy={row['strategy']} | "
        f"initial_cash={initial_cash_text} | benchmark={row['benchmark_ticker']} | "
        f"goal={goal_text} | learning={'on' if learning_enabled else 'off'} | "
        f"risk={row['risk_policy']} | instrument={row['instrument_mode']} | "
        f"created={row['created_at']}"
    )


def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    descriptive_name: str | None = None,
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str = "monthly",
    learning_enabled: bool = False,
    risk_policy: str = "none",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    instrument_mode: str = "equity",
    option_strike_offset_pct: float | None = None,
    option_min_dte: int | None = None,
    option_max_dte: int | None = None,
    option_type: str | None = None,
    target_delta_min: float | None = None,
    target_delta_max: float | None = None,
    max_premium_per_trade: float | None = None,
    max_contracts_per_trade: int | None = None,
    iv_rank_min: float | None = None,
    iv_rank_max: float | None = None,
    roll_dte_threshold: int | None = None,
    profit_take_pct: float | None = None,
    max_loss_pct: float | None = None,
) -> None:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    _validate_goal_return_range(goal_min_return_pct, goal_max_return_pct)

    display = (descriptive_name or name).strip()
    if not display:
        display = name

    risk = _normalize_risk_policy(risk_policy)
    mode = _normalize_instrument_mode(instrument_mode)
    _validate_option_settings(
        option_type,
        target_delta_min,
        target_delta_max,
        option_min_dte,
        option_max_dte,
        iv_rank_min,
        iv_rank_max,
    )

    try:
        conn.execute(
            """
            INSERT INTO accounts (
                name,
                strategy,
                initial_cash,
                created_at,
                benchmark_ticker,
                descriptive_name,
                goal_min_return_pct,
                goal_max_return_pct,
                goal_period,
                learning_enabled,
                risk_policy,
                stop_loss_pct,
                take_profit_pct,
                instrument_mode,
                option_strike_offset_pct,
                option_min_dte,
                option_max_dte,
                option_type,
                target_delta_min,
                target_delta_max,
                max_premium_per_trade,
                max_contracts_per_trade,
                iv_rank_min,
                iv_rank_max,
                roll_dte_threshold,
                profit_take_pct,
                max_loss_pct
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                strategy,
                float(initial_cash),
                utc_now_iso(),
                benchmark_ticker.upper().strip(),
                display,
                goal_min_return_pct,
                goal_max_return_pct,
                _normalize_lower(goal_period),
                int(learning_enabled),
                risk,
                stop_loss_pct,
                take_profit_pct,
                mode,
                option_strike_offset_pct,
                option_min_dte,
                option_max_dte,
                _normalize_option_type(option_type) if option_type else None,
                target_delta_min,
                target_delta_max,
                max_premium_per_trade,
                max_contracts_per_trade,
                iv_rank_min,
                iv_rank_max,
                roll_dte_threshold,
                profit_take_pct,
                max_loss_pct,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicateRecordError(f"Account '{name}' already exists.") from exc


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker.upper().strip(), account["id"]),
    )
    conn.commit()


def list_accounts(conn: sqlite3.Connection, by_strategy: bool = True) -> None:
    accounts = conn.execute("SELECT * FROM accounts ORDER BY strategy ASC, name ASC").fetchall()
    if not accounts:
        print("No paper accounts found.")
        return
    if by_strategy:
        current_strategy = None
        for account in accounts:
            if account["strategy"] != current_strategy:
                if current_strategy is not None:
                    print()
                current_strategy = account["strategy"]
                print(f"Strategy: {current_strategy}")
            print(f"  {_account_summary_line(account)}")
    else:
        for account in accounts:
            print(_account_summary_line(account))


def configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    descriptive_name: str | None = None,
    goal_min_return_pct: float | None = None,
    goal_max_return_pct: float | None = None,
    goal_period: str | None = None,
    learning_enabled: bool | None = None,
    risk_policy: str | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    instrument_mode: str | None = None,
    option_strike_offset_pct: float | None = None,
    option_min_dte: int | None = None,
    option_max_dte: int | None = None,
    option_type: str | None = None,
    target_delta_min: float | None = None,
    target_delta_max: float | None = None,
    max_premium_per_trade: float | None = None,
    max_contracts_per_trade: int | None = None,
    iv_rank_min: float | None = None,
    iv_rank_max: float | None = None,
    roll_dte_threshold: int | None = None,
    profit_take_pct: float | None = None,
    max_loss_pct: float | None = None,
) -> None:
    account = get_account(conn, account_name)
    updates: list[str] = []
    params: list[object] = []

    if descriptive_name is not None:
        display = descriptive_name.strip()
        if not display:
            raise ValueError("descriptive_name cannot be empty.")
        updates.append("descriptive_name = ?")
        params.append(display)

    _append_update(updates, params, "goal_period", goal_period, _normalize_lower_obj)
    _append_update(updates, params, "goal_min_return_pct", goal_min_return_pct, to_float_obj)
    _append_update(updates, params, "goal_max_return_pct", goal_max_return_pct, to_float_obj)
    _append_update(updates, params, "learning_enabled", learning_enabled, to_int_obj)

    if risk_policy is not None:
        _append_update(updates, params, "risk_policy", _normalize_risk_policy(risk_policy))

    if instrument_mode is not None:
        _append_update(updates, params, "instrument_mode", _normalize_instrument_mode(instrument_mode))

    if option_type is not None:
        _append_update(updates, params, "option_type", _normalize_option_type(option_type))

    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]] = [
        ("stop_loss_pct", stop_loss_pct, to_float_obj),
        ("take_profit_pct", take_profit_pct, to_float_obj),
        ("option_strike_offset_pct", option_strike_offset_pct, to_float_obj),
        ("option_min_dte", option_min_dte, to_int_obj),
        ("option_max_dte", option_max_dte, to_int_obj),
        ("target_delta_min", target_delta_min, to_float_obj),
        ("target_delta_max", target_delta_max, to_float_obj),
        ("max_premium_per_trade", max_premium_per_trade, to_float_obj),
        ("max_contracts_per_trade", max_contracts_per_trade, to_int_obj),
        ("iv_rank_min", iv_rank_min, to_float_obj),
        ("iv_rank_max", iv_rank_max, to_float_obj),
        ("roll_dte_threshold", roll_dte_threshold, to_int_obj),
        ("profit_take_pct", profit_take_pct, to_float_obj),
        ("max_loss_pct", max_loss_pct, to_float_obj),
    ]
    for column, value, transform in numeric_fields:
        _append_update(updates, params, column, value, transform)

    min_value = goal_min_return_pct if goal_min_return_pct is not None else row_float(account, "goal_min_return_pct")
    max_value = goal_max_return_pct if goal_max_return_pct is not None else row_float(account, "goal_max_return_pct")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    min_dte = option_min_dte if option_min_dte is not None else row_int(account, "option_min_dte")
    max_dte = option_max_dte if option_max_dte is not None else row_int(account, "option_max_dte")
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")

    delta_min = target_delta_min if target_delta_min is not None else row_float(account, "target_delta_min")
    delta_max = target_delta_max if target_delta_max is not None else row_float(account, "target_delta_max")
    iv_min = iv_rank_min if iv_rank_min is not None else row_float(account, "iv_rank_min")
    iv_max = iv_rank_max if iv_rank_max is not None else row_float(account, "iv_rank_max")
    resolved_opt_type = option_type if option_type is not None else row_str(account, "option_type")
    _validate_option_settings(
        resolved_opt_type,
        delta_min,
        delta_max,
        min_dte,
        max_dte,
        iv_min,
        iv_max,
    )

    if not updates:
        return

    params.append(account["id"])
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
