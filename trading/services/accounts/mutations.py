from __future__ import annotations

import sqlite3
from collections.abc import Callable

from common.time import utc_now_iso
from trading.domain.auto_trader_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.domain.exceptions import AccountAlreadyExistsError
from trading.models.account_config import AccountConfig
from trading.repositories.accounts_repository import (
    fetch_account_by_name as repo_fetch_account_by_name,
    insert_account,
    update_account_benchmark,
    update_account_fields,
)
from trading.services.accounts.config import (
    append_numeric_updates,
    append_update,
    normalize_instrument_mode,
    normalize_lower,
    normalize_lower_obj,
    normalize_option_type,
    normalize_risk_policy,
    validate_goal_range_from_inputs,
    validate_goal_return_range,
    validate_option_settings,
    validate_option_settings_from_inputs,
    validate_position_sizing,
    validate_position_sizing_from_inputs,
)
from trading.utils.coercion import to_float_obj, to_int_obj


def get_account(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    row = repo_fetch_account_by_name(conn, name)
    if row is None:
        raise ValueError(f"Account '{name}' not found.")
    return row


def update_account_fields_by_id(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    updates: list[str],
    params: list[object],
) -> None:
    update_account_fields(conn, account_id=account_id, updates=updates, params=params)


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
    validate_goal_return_range(cfg.goal_min_return_pct, cfg.goal_max_return_pct)

    display = (cfg.descriptive_name or name).strip()
    if not display:
        display = name

    risk = normalize_risk_policy(cfg.risk_policy or "none")
    mode = normalize_instrument_mode(cfg.instrument_mode or "equity")
    trade_size_pct = cfg.trade_size_pct if cfg.trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    max_position_pct = cfg.max_position_pct if cfg.max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    validate_position_sizing(trade_size_pct, max_position_pct)
    validate_option_settings(
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
            goal_period=normalize_lower(cfg.goal_period or "monthly"),
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
            option_type=normalize_option_type(cfg.option_type) if cfg.option_type else None,
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

    append_update(updates, params, "goal_period", cfg.goal_period, normalize_lower_obj)
    append_update(updates, params, "goal_min_return_pct", cfg.goal_min_return_pct, to_float_obj)
    append_update(updates, params, "goal_max_return_pct", cfg.goal_max_return_pct, to_float_obj)
    append_update(updates, params, "learning_enabled", cfg.learning_enabled, to_int_obj)

    if cfg.risk_policy is not None:
        append_update(updates, params, "risk_policy", normalize_risk_policy(cfg.risk_policy))

    if cfg.instrument_mode is not None:
        append_update(updates, params, "instrument_mode", normalize_instrument_mode(cfg.instrument_mode))

    if cfg.option_type is not None:
        append_update(updates, params, "option_type", normalize_option_type(cfg.option_type))

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
    append_numeric_updates(updates, params, numeric_fields)
    validate_goal_range_from_inputs(account, cfg.goal_min_return_pct, cfg.goal_max_return_pct)
    validate_position_sizing_from_inputs(account, cfg.trade_size_pct, cfg.max_position_pct)
    validate_option_settings_from_inputs(
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
