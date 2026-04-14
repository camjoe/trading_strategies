from __future__ import annotations

import sqlite3
from typing import Callable

from common.time import utc_now_iso
from trading.domain.auto_trader_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.domain.exceptions import AccountAlreadyExistsError
from trading.utils.coercion import (
    coerce_float,
    coerce_str,
    row_float,
    row_int,
    row_str,
    to_float_obj,
    to_int_obj,
)
from trading.models.account_config import AccountConfig
from trading.repositories.accounts_repository import (
    fetch_account_by_name as _repo_fetch_account_by_name,
    fetch_account_listing_rows,
    fetch_account_rows_excluding_name,
    fetch_all_account_names as _repo_fetch_all_account_names,
    fetch_all_account_names_from_conn,
    insert_account,
    update_account_benchmark,
    update_account_fields,
)
from trading.repositories.snapshots_repository import (
    fetch_latest_snapshot_row as _repo_fetch_latest_snapshot_row,
    fetch_snapshot_history_rows as _repo_fetch_snapshot_history_rows,
)

HEURISTIC_EXPLORATION_LABEL = "heuristic_exploration"
GOAL_NOT_SET_TEXT = "not-set"

RISK_POLICIES = {"none", "fixed_stop", "take_profit", "stop_and_target"}
INSTRUMENT_MODES = {"equity", "leaps"}
OPTION_TYPES = {"call", "put", "both"}

_ENUM_FIELDS = {
    "risk_policy": RISK_POLICIES,
    "instrument_mode": INSTRUMENT_MODES,
    "option_type": OPTION_TYPES,
}


# ---------------------------------------------------------------------------
# Account lookup
# ---------------------------------------------------------------------------

def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = _repo_fetch_account_by_name(conn, name)
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_goal_text(row: sqlite3.Row) -> str:
    min_goal = row_float(row, "goal_min_return_pct")
    max_goal = row_float(row, "goal_max_return_pct")
    goal_period = row_str(row, "goal_period") or "period"
    if min_goal is None and max_goal is None:
        return GOAL_NOT_SET_TEXT
    if min_goal is not None and max_goal is not None:
        return f"{min_goal:.2f}% to {max_goal:.2f}% per {goal_period}"
    if min_goal is not None:
        return f">= {min_goal:.2f}% per {goal_period}"
    return f"<= {max_goal:.2f}% per {goal_period}"


def _has_column(row: sqlite3.Row, column: str) -> bool:
    return column in row.keys()


def _resolve_base_and_active_strategy(row: sqlite3.Row) -> tuple[str, str]:
    base_strategy = str(row["strategy"])
    rotation_enabled = _has_column(row, "rotation_enabled") and bool(row_int(row, "rotation_enabled"))
    if not rotation_enabled:
        return base_strategy, base_strategy

    active_strategy = row_str(row, "rotation_active_strategy") or base_strategy
    return base_strategy, active_strategy


def format_account_policy_text(row: sqlite3.Row) -> str:
    base_strategy, active_strategy = _resolve_base_and_active_strategy(row)
    learning_enabled = row_int(row, "learning_enabled")
    trade_size_pct = row_float(row, "trade_size_pct")
    max_position_pct = row_float(row, "max_position_pct")
    resolved_trade_size_pct = (
        trade_size_pct if trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    )
    resolved_max_position_pct = (
        max_position_pct if max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    )
    return (
        f"base_strategy={base_strategy} | active_strategy={active_strategy} | "
        f"benchmark={row['benchmark_ticker']} | "
        f"{HEURISTIC_EXPLORATION_LABEL}={'on' if learning_enabled else 'off'} | "
        f"risk={row['risk_policy']} | instrument={row['instrument_mode']} | "
        f"trade_size={resolved_trade_size_pct:.2f}% | max_position={resolved_max_position_pct:.2f}%"
    )


def build_account_summary_line(row: sqlite3.Row) -> str:
    initial_cash = row_float(row, "initial_cash")
    initial_cash_text = f"{initial_cash:.2f}" if initial_cash is not None else "n/a"
    policy_text = format_account_policy_text(row)
    summary = (
        f"[{row['id']}] {row['name']} | display_name={row['descriptive_name']} | "
        f"initial_cash={initial_cash_text} | account_policy={policy_text} | "
        f"created={row['created_at']}"
    )
    goal_text = format_goal_text(row)
    if goal_text != GOAL_NOT_SET_TEXT:
        return f"{summary} | goal_metadata={goal_text}"
    return summary


def build_account_listing_lines(accounts: list[sqlite3.Row], *, by_strategy: bool) -> list[str]:
    lines: list[str] = []
    if by_strategy:
        current_strategy = None
        for account in accounts:
            if account["strategy"] != current_strategy:
                if current_strategy is not None:
                    lines.append("")
                current_strategy = account["strategy"]
                lines.append(f"Base Strategy: {current_strategy}")
            lines.append(f"  {build_account_summary_line(account)}")
        return lines
    for account in accounts:
        lines.append(build_account_summary_line(account))
    return lines


# ---------------------------------------------------------------------------
# Service-layer wrappers (read)
# ---------------------------------------------------------------------------

def fetch_account_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return _repo_fetch_account_by_name(conn, name)


def fetch_all_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names_from_conn(conn)


def fetch_account_rows_excluding(conn: sqlite3.Connection, *, excluded_name: str) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding_name(conn, excluded_name=excluded_name)


def fetch_latest_snapshot_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return _repo_fetch_latest_snapshot_row(conn, account_id=account_id)


def fetch_snapshot_history_rows(conn: sqlite3.Connection, account_id: int, *, limit: int) -> list[sqlite3.Row]:
    return _repo_fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def update_account_fields_by_id(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    updates: list[str],
    params: list[object],
) -> None:
    update_account_fields(conn, account_id=account_id, updates=updates, params=params)


# ---------------------------------------------------------------------------
# Validation helpers (private)
# ---------------------------------------------------------------------------

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


def _validate_range(
    min_val: object | None,
    max_val: object | None,
    field_prefix: str,
    min_name: str | None = None,
    max_name: str | None = None,
) -> None:
    """Helper to validate that min <= max for a pair of numeric fields."""
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


def _validate_or_none_range(value: object | None, min_bound: float, max_bound: float, field_name: str) -> None:
    """Validate that a value (if present) falls within [min_bound, max_bound]."""
    if value is None:
        return
    v = coerce_float(value)
    if v is None:
        raise ValueError(f"{field_name} must be numeric.")
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


def _resolve_sizing_value(
    value: float | None,
    row: sqlite3.Row,
    column: str,
    default: float,
) -> float:
    if value is not None:
        return value
    existing = row_float(row, column)
    if existing is not None:
        return existing
    return default


def _validate_position_sizing(
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


def _validate_position_sizing_from_inputs(
    account: sqlite3.Row,
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> tuple[float, float]:
    resolved_trade_size_pct = _resolve_sizing_value(
        trade_size_pct,
        account,
        "trade_size_pct",
        DEFAULT_TRADE_SIZE_PCT,
    )
    resolved_max_position_pct = _resolve_sizing_value(
        max_position_pct,
        account,
        "max_position_pct",
        DEFAULT_MAX_POSITION_PCT,
    )
    _validate_position_sizing(resolved_trade_size_pct, resolved_max_position_pct)
    return resolved_trade_size_pct, resolved_max_position_pct


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


def _append_numeric_updates(
    updates: list[str],
    params: list[object],
    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]],
) -> None:
    for column, value, transform in numeric_fields:
        _append_update(updates, params, column, value, transform)


def _resolved_float(value: float | None, row: sqlite3.Row, column: str) -> float | None:
    if value is not None:
        return value
    return row_float(row, column)


def _resolved_int(value: int | None, row: sqlite3.Row, column: str) -> int | None:
    if value is not None:
        return value
    return row_int(row, column)


def _validate_goal_range_from_inputs(
    account: sqlite3.Row,
    goal_min_return_pct: float | None,
    goal_max_return_pct: float | None,
) -> None:
    min_value = _resolved_float(goal_min_return_pct, account, "goal_min_return_pct")
    max_value = _resolved_float(goal_max_return_pct, account, "goal_max_return_pct")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("goal_min_return_pct cannot be greater than goal_max_return_pct.")


def _validate_option_settings_from_inputs(
    account: sqlite3.Row,
    option_type: str | None,
    target_delta_min: float | None,
    target_delta_max: float | None,
    option_min_dte: int | None,
    option_max_dte: int | None,
    iv_rank_min: float | None,
    iv_rank_max: float | None,
) -> None:
    min_dte = _resolved_int(option_min_dte, account, "option_min_dte")
    max_dte = _resolved_int(option_max_dte, account, "option_max_dte")
    if min_dte is not None and max_dte is not None and min_dte > max_dte:
        raise ValueError("option_min_dte cannot be greater than option_max_dte.")
    delta_min = _resolved_float(target_delta_min, account, "target_delta_min")
    delta_max = _resolved_float(target_delta_max, account, "target_delta_max")
    iv_min = _resolved_float(iv_rank_min, account, "iv_rank_min")
    iv_max = _resolved_float(iv_rank_max, account, "iv_rank_max")
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


# ---------------------------------------------------------------------------
# Account management (write)
# ---------------------------------------------------------------------------

def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    config: AccountConfig | None = None,
) -> None:
    from trading.backtesting.domain.strategy_signals import validate_strategy_name

    cfg = config or AccountConfig()
    if initial_cash <= 0:
        raise ValueError("initial_cash must be greater than 0.")
    validate_strategy_name(strategy)
    _validate_goal_return_range(cfg.goal_min_return_pct, cfg.goal_max_return_pct)

    display = (cfg.descriptive_name or name).strip()
    if not display:
        display = name

    risk = _normalize_risk_policy(cfg.risk_policy or "none")
    mode = _normalize_instrument_mode(cfg.instrument_mode or "equity")
    trade_size_pct = (
        cfg.trade_size_pct if cfg.trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    )
    max_position_pct = (
        cfg.max_position_pct if cfg.max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    )
    _validate_position_sizing(trade_size_pct, max_position_pct)
    _validate_option_settings(
        cfg.option_type,
        cfg.target_delta_min,
        cfg.target_delta_max,
        cfg.option_min_dte,
        cfg.option_max_dte,
        cfg.iv_rank_min,
        cfg.iv_rank_max,
    )

    try:
        insert_account(
            conn,
            name=name,
            strategy=strategy,
            initial_cash=float(initial_cash),
            created_at=utc_now_iso(),
            benchmark_ticker=benchmark_ticker.upper().strip(),
            descriptive_name=display,
            goal_min_return_pct=cfg.goal_min_return_pct,
            goal_max_return_pct=cfg.goal_max_return_pct,
            goal_period=_normalize_lower(cfg.goal_period or "monthly"),
            learning_enabled=int(cfg.learning_enabled if cfg.learning_enabled is not None else False),
            risk_policy=risk,
            stop_loss_pct=cfg.stop_loss_pct,
            take_profit_pct=cfg.take_profit_pct,
            trade_size_pct=trade_size_pct,
            max_position_pct=max_position_pct,
            instrument_mode=mode,
            option_strike_offset_pct=cfg.option_strike_offset_pct,
            option_min_dte=cfg.option_min_dte,
            option_max_dte=cfg.option_max_dte,
            option_type=_normalize_option_type(cfg.option_type) if cfg.option_type else None,
            target_delta_min=cfg.target_delta_min,
            target_delta_max=cfg.target_delta_max,
            max_premium_per_trade=cfg.max_premium_per_trade,
            max_contracts_per_trade=cfg.max_contracts_per_trade,
            iv_rank_min=cfg.iv_rank_min,
            iv_rank_max=cfg.iv_rank_max,
            roll_dte_threshold=cfg.roll_dte_threshold,
            profit_take_pct=cfg.profit_take_pct,
            max_loss_pct=cfg.max_loss_pct,
        )
    except sqlite3.IntegrityError as exc:
        raise AccountAlreadyExistsError(f"Account '{name}' already exists.") from exc


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    update_account_benchmark(
        conn,
        account_id=account["id"],
        benchmark_ticker=benchmark_ticker.upper().strip(),
    )


def list_accounts(conn: sqlite3.Connection, by_strategy: bool = True) -> None:
    accounts = fetch_account_listing_rows(conn)
    if not accounts:
        print("No paper accounts found.")
        return
    for line in build_account_listing_lines(accounts, by_strategy=by_strategy):
        print(line)


def configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    config: AccountConfig | None = None,
) -> None:
    cfg = config or AccountConfig()
    account = get_account(conn, account_name)
    updates: list[str] = []
    params: list[object] = []

    if cfg.descriptive_name is not None:
        display = cfg.descriptive_name.strip()
        if not display:
            raise ValueError("descriptive_name cannot be empty.")
        updates.append("descriptive_name = ?")
        params.append(display)

    _append_update(updates, params, "goal_period", cfg.goal_period, _normalize_lower_obj)
    _append_update(updates, params, "goal_min_return_pct", cfg.goal_min_return_pct, to_float_obj)
    _append_update(updates, params, "goal_max_return_pct", cfg.goal_max_return_pct, to_float_obj)
    _append_update(updates, params, "learning_enabled", cfg.learning_enabled, to_int_obj)

    if cfg.risk_policy is not None:
        _append_update(updates, params, "risk_policy", _normalize_risk_policy(cfg.risk_policy))

    if cfg.instrument_mode is not None:
        _append_update(updates, params, "instrument_mode", _normalize_instrument_mode(cfg.instrument_mode))

    if cfg.option_type is not None:
        _append_update(updates, params, "option_type", _normalize_option_type(cfg.option_type))

    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]] = [
        ("stop_loss_pct", cfg.stop_loss_pct, to_float_obj),
        ("take_profit_pct", cfg.take_profit_pct, to_float_obj),
        ("trade_size_pct", cfg.trade_size_pct, to_float_obj),
        ("max_position_pct", cfg.max_position_pct, to_float_obj),
        ("option_strike_offset_pct", cfg.option_strike_offset_pct, to_float_obj),
        ("option_min_dte", cfg.option_min_dte, to_int_obj),
        ("option_max_dte", cfg.option_max_dte, to_int_obj),
        ("target_delta_min", cfg.target_delta_min, to_float_obj),
        ("target_delta_max", cfg.target_delta_max, to_float_obj),
        ("max_premium_per_trade", cfg.max_premium_per_trade, to_float_obj),
        ("max_contracts_per_trade", cfg.max_contracts_per_trade, to_int_obj),
        ("iv_rank_min", cfg.iv_rank_min, to_float_obj),
        ("iv_rank_max", cfg.iv_rank_max, to_float_obj),
        ("roll_dte_threshold", cfg.roll_dte_threshold, to_int_obj),
        ("profit_take_pct", cfg.profit_take_pct, to_float_obj),
        ("max_loss_pct", cfg.max_loss_pct, to_float_obj),
    ]
    _append_numeric_updates(updates, params, numeric_fields)
    _validate_goal_range_from_inputs(account, cfg.goal_min_return_pct, cfg.goal_max_return_pct)
    _validate_position_sizing_from_inputs(account, cfg.trade_size_pct, cfg.max_position_pct)
    _validate_option_settings_from_inputs(
        account,
        cfg.option_type,
        cfg.target_delta_min,
        cfg.target_delta_max,
        cfg.option_min_dte,
        cfg.option_max_dte,
        cfg.iv_rank_min,
        cfg.iv_rank_max,
    )

    if not updates:
        return

    update_account_fields(
        conn,
        account_id=account["id"],
        updates=updates,
        params=params,
    )


def load_all_account_names() -> list[str]:
    return _repo_fetch_all_account_names()


def create_managed_account(
    conn: sqlite3.Connection,
    *,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    config: AccountConfig,
) -> None:
    create_account(
        conn,
        name=name,
        strategy=strategy,
        initial_cash=initial_cash,
        benchmark_ticker=benchmark_ticker,
        config=config,
    )
