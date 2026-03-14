import sqlite3
from datetime import datetime, timezone
from typing import Callable


RISK_POLICIES = {"none", "fixed_stop", "take_profit", "stop_and_target"}
INSTRUMENT_MODES = {"equity", "leaps"}
OPTION_TYPES = {"call", "put", "both"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


def _normalize_lower(value: str) -> str:
    return value.strip().lower()


def _normalize_risk_policy(risk_policy: str) -> str:
    risk = _normalize_lower(risk_policy)
    if risk not in RISK_POLICIES:
        raise ValueError("risk_policy must be one of: none, fixed_stop, take_profit, stop_and_target")
    return risk


def _normalize_instrument_mode(instrument_mode: str) -> str:
    mode = _normalize_lower(instrument_mode)
    if mode not in INSTRUMENT_MODES:
        raise ValueError("instrument_mode must be one of: equity, leaps")
    return mode


def _normalize_option_type(option_type: str) -> str:
    opt_type = _normalize_lower(option_type)
    if opt_type not in OPTION_TYPES:
        raise ValueError("option_type must be one of: call, put, both")
    return opt_type


def _validate_goal_return_range(goal_min_return_pct: float | None, goal_max_return_pct: float | None) -> None:
    if goal_min_return_pct is not None and goal_max_return_pct is not None:
        if goal_min_return_pct > goal_max_return_pct:
            raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def _resolve_setting(new_value: object | None, current_value: object | None) -> object | None:
    return new_value if new_value is not None else current_value


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


def _goal_text(row: sqlite3.Row) -> str:
    if row["goal_min_return_pct"] is None and row["goal_max_return_pct"] is None:
        return "not-set"
    if row["goal_min_return_pct"] is not None and row["goal_max_return_pct"] is not None:
        return (
            f"{float(row['goal_min_return_pct']):.2f}% to "
            f"{float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"
        )
    if row["goal_min_return_pct"] is not None:
        return f">= {float(row['goal_min_return_pct']):.2f}% per {row['goal_period']}"
    return f"<= {float(row['goal_max_return_pct']):.2f}% per {row['goal_period']}"


def _account_summary_line(row: sqlite3.Row) -> str:
    goal_text = _goal_text(row)
    return (
        f"[{row['id']}] {row['name']} ({row['descriptive_name']}) | strategy={row['strategy']} | "
        f"initial_cash={row['initial_cash']:.2f} | benchmark={row['benchmark_ticker']} | "
        f"goal={goal_text} | learning={'on' if int(row['learning_enabled']) else 'off'} | "
        f"risk={row['risk_policy']} | instrument={row['instrument_mode']} | "
        f"created={row['created_at']}"
    )


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
    if target_delta_min is not None and not (0 <= float(target_delta_min) <= 1):
        raise ValueError("target_delta_min must be between 0 and 1.")
    if target_delta_max is not None and not (0 <= float(target_delta_max) <= 1):
        raise ValueError("target_delta_max must be between 0 and 1.")
    if (
        target_delta_min is not None
        and target_delta_max is not None
        and float(target_delta_min) > float(target_delta_max)
    ):
        raise ValueError("target_delta_min cannot be greater than target_delta_max.")
    if option_min_dte is not None and int(option_min_dte) < 0:
        raise ValueError("option_min_dte must be >= 0.")
    if option_max_dte is not None and int(option_max_dte) < 0:
        raise ValueError("option_max_dte must be >= 0.")
    if option_min_dte is not None and option_max_dte is not None and int(option_min_dte) > int(option_max_dte):
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    if iv_rank_min is not None and not (0 <= float(iv_rank_min) <= 100):
        raise ValueError("iv_rank_min must be between 0 and 100.")
    if iv_rank_max is not None and not (0 <= float(iv_rank_max) <= 100):
        raise ValueError("iv_rank_max must be between 0 and 100.")
    if iv_rank_min is not None and iv_rank_max is not None and float(iv_rank_min) > float(iv_rank_max):
        raise ValueError("iv_rank_min cannot be greater than iv_rank_max.")


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
    if option_min_dte is not None and option_max_dte is not None and option_min_dte > option_max_dte:
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    _validate_option_settings(
        option_type,
        target_delta_min,
        target_delta_max,
        option_min_dte,
        option_max_dte,
        iv_rank_min,
        iv_rank_max,
    )

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


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    conn.execute(
        "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
        (benchmark_ticker.upper().strip(), account["id"]),
    )
    conn.commit()


def list_accounts(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT id, name, descriptive_name, strategy, initial_cash, created_at, benchmark_ticker,
             goal_min_return_pct, goal_max_return_pct, goal_period, learning_enabled,
             risk_policy, stop_loss_pct, take_profit_pct, instrument_mode,
             option_strike_offset_pct, option_min_dte, option_max_dte,
             option_type, target_delta_min, target_delta_max,
             max_premium_per_trade, max_contracts_per_trade,
             iv_rank_min, iv_rank_max, roll_dte_threshold,
             profit_take_pct, max_loss_pct
        FROM accounts
        ORDER BY id
        """
    ).fetchall()
    if not rows:
        print("No paper accounts found.")
        return

    for row in rows:
        print(_account_summary_line(row))


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

    _append_update(updates, params, "goal_period", goal_period, _normalize_lower)
    _append_update(updates, params, "goal_min_return_pct", goal_min_return_pct, float)
    _append_update(updates, params, "goal_max_return_pct", goal_max_return_pct, float)
    _append_update(updates, params, "learning_enabled", learning_enabled, int)

    if risk_policy is not None:
        _append_update(updates, params, "risk_policy", _normalize_risk_policy(risk_policy))

    if instrument_mode is not None:
        _append_update(updates, params, "instrument_mode", _normalize_instrument_mode(instrument_mode))

    if option_type is not None:
        _append_update(updates, params, "option_type", _normalize_option_type(option_type))

    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]] = [
        ("stop_loss_pct", stop_loss_pct, float),
        ("take_profit_pct", take_profit_pct, float),
        ("option_strike_offset_pct", option_strike_offset_pct, float),
        ("option_min_dte", option_min_dte, int),
        ("option_max_dte", option_max_dte, int),
        ("target_delta_min", target_delta_min, float),
        ("target_delta_max", target_delta_max, float),
        ("max_premium_per_trade", max_premium_per_trade, float),
        ("max_contracts_per_trade", max_contracts_per_trade, int),
        ("iv_rank_min", iv_rank_min, float),
        ("iv_rank_max", iv_rank_max, float),
        ("roll_dte_threshold", roll_dte_threshold, int),
        ("profit_take_pct", profit_take_pct, float),
        ("max_loss_pct", max_loss_pct, float),
    ]
    for column, value, transform in numeric_fields:
        _append_update(updates, params, column, value, transform)

    min_value = _resolve_setting(goal_min_return_pct, account["goal_min_return_pct"])
    max_value = _resolve_setting(goal_max_return_pct, account["goal_max_return_pct"])
    if min_value is not None and max_value is not None and float(min_value) > float(max_value):
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")

    min_dte = _resolve_setting(option_min_dte, account["option_min_dte"])
    max_dte = _resolve_setting(option_max_dte, account["option_max_dte"])
    if min_dte is not None and max_dte is not None and int(min_dte) > int(max_dte):
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")

    delta_min = _resolve_setting(target_delta_min, account["target_delta_min"])
    delta_max = _resolve_setting(target_delta_max, account["target_delta_max"])
    iv_min = _resolve_setting(iv_rank_min, account["iv_rank_min"])
    iv_max = _resolve_setting(iv_rank_max, account["iv_rank_max"])
    resolved_opt_type = _resolve_setting(option_type, account["option_type"])
    _validate_option_settings(
        resolved_opt_type,
        float(delta_min) if delta_min is not None else None,
        float(delta_max) if delta_max is not None else None,
        int(min_dte) if min_dte is not None else None,
        int(max_dte) if max_dte is not None else None,
        float(iv_min) if iv_min is not None else None,
        float(iv_max) if iv_max is not None else None,
    )

    if not updates:
        return

    params.append(account["id"])
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", tuple(params))
    conn.commit()
