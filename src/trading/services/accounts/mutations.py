from __future__ import annotations

import json
import sqlite3

from common.coercion import expect_float, expect_int
from common.time import utc_now_iso
from trading.domain.auto_trading_policy import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.domain.exceptions import AccountAlreadyExistsError, NotFoundError, ValidationError
from trading.models import AccountConfig, AccountInsert, AccountRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.services.accounts.config import (
    normalize_instrument_mode,
    normalize_lower,
    normalize_option_type,
    normalize_risk_policy,
    validate_goal_range_from_inputs,
    validate_goal_return_range,
    validate_option_settings,
    validate_option_settings_from_inputs,
    validate_position_sizing,
    validate_position_sizing_from_inputs,
)
from trading.services.accounts.queries import find_account
from trading.services.books.book_assignments import sync_default_book_assignment
from trading.services.universe import default_trade_symbols, resolve_trade_symbols


def get_account(conn: sqlite3.Connection, name: str) -> AccountRecord:
    row = find_account(conn, name)
    if row is None:
        raise NotFoundError(f"Account '{name}' not found.")
    return row


def _serialize_trade_symbols(symbols: list[str]) -> str:
    return json.dumps(symbols, separators=(",", ":"))


def _apply_book_settings_to_default_book(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    values: dict[str, object | None],
) -> None:
    """Write execution/option settings (book columns since revisions
    0004/0005) to the account's default book; None values are skipped (keep
    current/DDL value)."""
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    if book is None:
        raise NotFoundError(f"Default book missing for account id {account_id}.")
    BookRepository(conn).update_settings(
        book_id=book.id,
        values={column: value for column, value in values.items() if value is not None},
    )


def set_account_strategy(conn: sqlite3.Connection, account_name: str, strategy: str) -> None:
    from trading.domain.strategies.resolution import validate_strategy_name

    normalized_strategy = strategy.strip()
    if not normalized_strategy:
        raise ValidationError("strategy cannot be empty.")
    validate_strategy_name(normalized_strategy)
    account = get_account(conn, account_name)
    # Strategy truth is the default book's assignment (accounts.strategy was
    # dropped in revision 0008).
    sync_default_book_assignment(
        conn,
        account_id=account.id,
        strategy_name=normalized_strategy,
        now_iso=utc_now_iso(),
    )


def _create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    config: AccountConfig | None = None,
) -> None:
    from trading.domain.strategies.resolution import validate_strategy_name

    cfg = config or AccountConfig()
    if initial_cash <= 0:
        raise ValidationError("initial_cash must be greater than 0.")
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

    created_ts = utc_now_iso()
    try:
        AccountRepository(conn).insert(
            AccountInsert(
                name=name,
                initial_cash=float(initial_cash),
                created_at=created_ts,
                updated_at=created_ts,
                benchmark_ticker=benchmark_ticker.upper().strip(),
                descriptive_name=display,
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
    # Execution/option settings are book columns (revisions 0004/0005): apply
    # the validated create-time values to the default book the bootstrap just
    # ensured.
    _apply_book_settings_to_default_book(
        conn,
        account_id=account.id,
        values={
            "learning_enabled": int(cfg.learning_enabled if cfg.learning_enabled is not None else False),
            "risk_policy": risk,
            "stop_loss_pct": cfg.stop_loss_pct,
            "take_profit_pct": cfg.take_profit_pct,
            "trade_size_pct": trade_size_pct,
            "max_position_pct": max_position_pct,
            "instrument_mode": mode,
            "option_profit_take_pct": cfg.option_profit_take_pct,
            "option_max_loss_pct": cfg.option_max_loss_pct,
            "option_strike_offset_pct": cfg.option_strike_offset_pct,
            "option_min_dte": cfg.option_min_dte,
            "option_max_dte": cfg.option_max_dte,
            "option_type": normalize_option_type(cfg.option_type) if cfg.option_type else None,
            "target_delta_min": cfg.target_delta_min,
            "target_delta_max": cfg.target_delta_max,
            "max_premium_per_trade": cfg.max_premium_per_trade,
            "max_contracts_per_trade": cfg.max_contracts_per_trade,
            "iv_rank_min": cfg.iv_rank_min,
            "iv_rank_max": cfg.iv_rank_max,
            "roll_dte_threshold": cfg.roll_dte_threshold,
            "goal_min_return_pct": cfg.goal_min_return_pct,
            "goal_max_return_pct": cfg.goal_max_return_pct,
            "goal_period": normalize_lower(cfg.goal_period or "monthly"),
        },
    )
    # Always land a resolved symbol list: the bootstrap leaves the book empty
    # (it cannot resolve a universe name), so a new account with no universes
    # named would otherwise trade nothing.
    if cfg.trade_universes is not None:
        _apply_trade_universes_to_default_book(conn, account_id=account.id, names=cfg.trade_universes)
    else:
        _apply_trade_symbols_to_default_book(conn, account_id=account.id, symbols=default_trade_symbols())


def create_account(
    conn: sqlite3.Connection,
    name: str,
    strategy: str,
    initial_cash: float,
    benchmark_ticker: str,
    config: AccountConfig | None = None,
) -> None:
    """Create an account and all required book-owned state atomically."""
    with unit_of_work(conn):
        _create_account(conn, name, strategy, initial_cash, benchmark_ticker, config)


def _apply_trade_universes_to_default_book(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    names: list[str],
) -> None:
    """Expand universe *names* and store the resulting symbols on the default book.

    Names are the caller's shorthand; the book keeps the tickers (revision
    0029), so an unresolvable name fails here rather than at trade time, and
    later edits to a universe file leave this book's symbols alone.
    """
    _apply_trade_symbols_to_default_book(conn, account_id=account_id, symbols=resolve_trade_symbols(names))


def _apply_trade_symbols_to_default_book(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    symbols: list[str],
) -> None:
    """Set the default book's tradeable symbols (history-recorded; revision 0008)."""
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    if book is None:
        raise NotFoundError(f"Default book missing for account id {account_id}.")
    BookRepository(conn).update_trade_symbols(
        book_id=book.id,
        trade_symbols=_serialize_trade_symbols(symbols),
        updated_at=utc_now_iso(),
    )


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    AccountRepository(conn).update_benchmark(
        account_id=account.id,
        benchmark_ticker=benchmark_ticker.upper().strip(),
        updated_at=utc_now_iso(),
    )


def _configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    config: AccountConfig | None = None,
) -> None:
    cfg = config or AccountConfig()
    account = get_account(conn, account_name)
    account_values: dict[str, object] = {}

    if cfg.descriptive_name is not None:
        display = cfg.descriptive_name.strip()
        if not display:
            raise ValidationError("descriptive_name cannot be empty.")
        account_values["descriptive_name"] = display

    # Goals, universes, and execution/option knobs are book columns
    # (revisions 0004/0005/0008): validate merged over the default book's
    # current values, then write to the book.
    default_book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    validate_goal_range_from_inputs(
        default_book if default_book is not None else {},
        cfg.goal_min_return_pct,
        cfg.goal_max_return_pct,
    )
    validate_position_sizing_from_inputs(
        default_book.trade_size_pct if default_book is not None else None,
        default_book.max_position_pct if default_book is not None else None,
        cfg.trade_size_pct,
        cfg.max_position_pct,
    )
    validate_option_settings_from_inputs(
        default_book if default_book is not None else {},
        cfg.option_type,
        cfg.target_delta_min,
        cfg.target_delta_max,
        cfg.option_min_dte,
        cfg.option_max_dte,
        cfg.iv_rank_min,
        cfg.iv_rank_max,
    )

    _apply_book_settings_to_default_book(
        conn,
        account_id=account.id,
        values={
            "learning_enabled": expect_int(cfg.learning_enabled) if cfg.learning_enabled is not None else None,
            "risk_policy": normalize_risk_policy(cfg.risk_policy) if cfg.risk_policy is not None else None,
            "instrument_mode": (
                normalize_instrument_mode(cfg.instrument_mode) if cfg.instrument_mode is not None else None
            ),
            "stop_loss_pct": expect_float(cfg.stop_loss_pct) if cfg.stop_loss_pct is not None else None,
            "take_profit_pct": expect_float(cfg.take_profit_pct) if cfg.take_profit_pct is not None else None,
            "trade_size_pct": expect_float(cfg.trade_size_pct) if cfg.trade_size_pct is not None else None,
            "max_position_pct": expect_float(cfg.max_position_pct) if cfg.max_position_pct is not None else None,
            "option_profit_take_pct": expect_float(cfg.option_profit_take_pct)
            if cfg.option_profit_take_pct is not None
            else None,
            "option_max_loss_pct": expect_float(cfg.option_max_loss_pct)
            if cfg.option_max_loss_pct is not None
            else None,
            "option_type": normalize_option_type(cfg.option_type) if cfg.option_type is not None else None,
            "option_strike_offset_pct": (
                expect_float(cfg.option_strike_offset_pct) if cfg.option_strike_offset_pct is not None else None
            ),
            "option_min_dte": expect_int(cfg.option_min_dte) if cfg.option_min_dte is not None else None,
            "option_max_dte": expect_int(cfg.option_max_dte) if cfg.option_max_dte is not None else None,
            "target_delta_min": expect_float(cfg.target_delta_min) if cfg.target_delta_min is not None else None,
            "target_delta_max": expect_float(cfg.target_delta_max) if cfg.target_delta_max is not None else None,
            "max_premium_per_trade": (
                expect_float(cfg.max_premium_per_trade) if cfg.max_premium_per_trade is not None else None
            ),
            "max_contracts_per_trade": (
                expect_int(cfg.max_contracts_per_trade) if cfg.max_contracts_per_trade is not None else None
            ),
            "iv_rank_min": expect_float(cfg.iv_rank_min) if cfg.iv_rank_min is not None else None,
            "iv_rank_max": expect_float(cfg.iv_rank_max) if cfg.iv_rank_max is not None else None,
            "roll_dte_threshold": expect_int(cfg.roll_dte_threshold) if cfg.roll_dte_threshold is not None else None,
            "goal_min_return_pct": expect_float(cfg.goal_min_return_pct)
            if cfg.goal_min_return_pct is not None
            else None,
            "goal_max_return_pct": expect_float(cfg.goal_max_return_pct)
            if cfg.goal_max_return_pct is not None
            else None,
            "goal_period": normalize_lower(cfg.goal_period) if cfg.goal_period is not None else None,
        },
    )
    if cfg.trade_universes is not None:
        _apply_trade_universes_to_default_book(conn, account_id=account.id, names=cfg.trade_universes)

    AccountRepository(conn).update(
        account_id=account.id,
        values=account_values,
        updated_at=utc_now_iso(),
    )


def configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    config: AccountConfig | None = None,
) -> None:
    """Apply one account configuration request atomically."""
    with unit_of_work(conn):
        _configure_account(conn, account_name, config)
