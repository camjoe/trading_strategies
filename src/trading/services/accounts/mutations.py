from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

from common.coercion import expect_float, expect_int
from common.time import utc_now_iso
from trading.domain.auto_trading_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.domain.exceptions import AccountAlreadyExistsError, NotFoundError, ValidationError
from trading.models import AccountConfig, AccountInsert, AccountRecord
from trading.repositories.accounts import AccountRepository
from trading.services.accounts.queries import find_account
from trading.services.books.book_assignments import sync_default_book_assignment
from trading.services.accounts.config import (
    ACCOUNT_KIND_MANAGED,
    append_numeric_updates,
    append_update,
    normalize_account_kind,
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


def get_account(conn: sqlite3.Connection, name: str) -> AccountRecord:
    row = find_account(conn, name)
    if row is None:
        raise NotFoundError(f"Account '{name}' not found.")
    return row


def _serialize_trade_universes(names: list[str]) -> str:
    return json.dumps(names, separators=(",", ":"))


def set_account_strategy(conn: sqlite3.Connection, account_name: str, strategy: str) -> None:
    from trading.domain.strategy_signals import validate_strategy_name

    normalized_strategy = strategy.strip()
    if not normalized_strategy:
        raise ValidationError("strategy cannot be empty.")
    validate_strategy_name(normalized_strategy)
    account = get_account(conn, account_name)
    AccountRepository(conn).update(
        account_id=account.id,
        updates=["strategy = ?"],
        params=[normalized_strategy],
    )
    # The default book's assignment is what actually trades; keep it in step
    # with the account's strategy column.
    sync_default_book_assignment(
        conn,
        account_id=account.id,
        strategy_name=normalized_strategy,
        now_iso=utc_now_iso(),
    )


def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    config: AccountConfig | None = None,
) -> None:
    from trading.domain.strategy_signals import validate_strategy_name

    cfg = config or AccountConfig()
    if initial_cash <= 0:
        raise ValidationError("initial_cash must be greater than 0.")
    validate_strategy_name(strategy)
    validate_goal_return_range(cfg.goal_min_return_pct, cfg.goal_max_return_pct)

    display = (cfg.descriptive_name or name).strip()
    if not display:
        display = name

    account_kind = normalize_account_kind(cfg.account_kind or ACCOUNT_KIND_MANAGED)
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
        AccountRepository(conn).insert(
            AccountInsert(
                name=name,
                account_kind=account_kind,
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
                trade_universes=(
                    _serialize_trade_universes(cfg.trade_universes) if cfg.trade_universes is not None else None
                ),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise AccountAlreadyExistsError(f"Account '{name}' already exists.") from exc

    # Bootstrap the default book and open its assignment so the new account
    # trades from day one (books are the execution primitive; ADR 010/014).
    account = get_account(conn, name)
    sync_default_book_assignment(
        conn,
        account_id=account.id,
        strategy_name=strategy,
        now_iso=utc_now_iso(),
    )


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    AccountRepository(conn).update_benchmark(
        account_id=account.id,
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
            raise ValidationError("descriptive_name cannot be empty.")
        updates.append("descriptive_name = ?")
        params.append(display)

    if cfg.account_kind is not None:
        append_update(updates, params, "account_kind", normalize_account_kind(cfg.account_kind))

    append_update(updates, params, "goal_period", cfg.goal_period, normalize_lower_obj)
    append_update(updates, params, "goal_min_return_pct", cfg.goal_min_return_pct, expect_float)
    append_update(updates, params, "goal_max_return_pct", cfg.goal_max_return_pct, expect_float)
    append_update(updates, params, "learning_enabled", cfg.learning_enabled, expect_int)

    if cfg.risk_policy is not None:
        append_update(updates, params, "risk_policy", normalize_risk_policy(cfg.risk_policy))

    if cfg.instrument_mode is not None:
        append_update(updates, params, "instrument_mode", normalize_instrument_mode(cfg.instrument_mode))

    if cfg.option_type is not None:
        append_update(updates, params, "option_type", normalize_option_type(cfg.option_type))

    numeric_fields: list[tuple[str, object | None, Callable[[object], object]]] = [
        ("stop_loss_pct", cfg.stop_loss_pct, expect_float),
        ("take_profit_pct", cfg.take_profit_pct, expect_float),
        ("trade_size_pct", cfg.trade_size_pct, expect_float),
        ("max_position_pct", cfg.max_position_pct, expect_float),
        ("option_strike_offset_pct", cfg.option_strike_offset_pct, expect_float),
        ("option_min_dte", cfg.option_min_dte, expect_int),
        ("option_max_dte", cfg.option_max_dte, expect_int),
        ("target_delta_min", cfg.target_delta_min, expect_float),
        ("target_delta_max", cfg.target_delta_max, expect_float),
        ("max_premium_per_trade", cfg.max_premium_per_trade, expect_float),
        ("max_contracts_per_trade", cfg.max_contracts_per_trade, expect_int),
        ("iv_rank_min", cfg.iv_rank_min, expect_float),
        ("iv_rank_max", cfg.iv_rank_max, expect_float),
        ("roll_dte_threshold", cfg.roll_dte_threshold, expect_int),
        ("profit_take_pct", cfg.profit_take_pct, expect_float),
        ("max_loss_pct", cfg.max_loss_pct, expect_float),
    ]
    append_numeric_updates(updates, params, numeric_fields)

    if cfg.trade_universes is not None:
        updates.append("trade_universes = ?")
        params.append(_serialize_trade_universes(cfg.trade_universes))
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

    AccountRepository(conn).update(
        account_id=account.id,
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
