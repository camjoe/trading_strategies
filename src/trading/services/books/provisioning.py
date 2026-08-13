"""Provision an account's default book at creation time.

The book side of account creation: books are the execution primitive (ADR
010/014), so a new account gets a default book that trades from day one. The
account create path resolves identity and then calls ``bootstrap_default_book``;
``ensure_default_books`` (in ``strategy_catalog``) is the separate repair path
for accounts that predate the default-book model.
"""

from __future__ import annotations

import sqlite3

from common.json_columns import dumps_json_column
from trading.domain.auto_trading.sizing import DEFAULT_MAX_POSITION_PCT, DEFAULT_TRADE_SIZE_PCT
from trading.models.accounts import AccountConfig
from trading.models.books import BookSettingsUpdate
from trading.repositories.books import BookRepository
from trading.services.books.book_assignments import sync_default_book_assignment
from trading.services.books.settings_validation import (
    normalize_instrument_mode,
    normalize_lower,
    normalize_option_type,
    normalize_risk_policy,
    validate_goal_return_range,
    validate_option_settings,
    validate_position_sizing,
)
from trading.services.universe import default_trade_symbols, resolve_trade_symbols


def bootstrap_default_book(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy: str,
    initial_cash: float,
    config: AccountConfig,
    now_iso: str,
) -> None:
    """Create the account's default book, open its assignment, and write create-time settings.

    Validates the create-time book settings, resolves the trade universe, inserts
    the default book with opening balances, opens its strategy assignment, then
    writes the validated execution/goal/option columns. Runs inside the caller's
    ``unit_of_work``, so any failure rolls the whole account create back.
    """
    validate_goal_return_range(config.goal_min_return_pct, config.goal_max_return_pct)
    risk = normalize_risk_policy(config.risk_policy or "none")
    mode = normalize_instrument_mode(config.instrument_mode or "equity")
    trade_size_pct = config.trade_size_pct if config.trade_size_pct is not None else DEFAULT_TRADE_SIZE_PCT
    max_position_pct = config.max_position_pct if config.max_position_pct is not None else DEFAULT_MAX_POSITION_PCT
    validate_position_sizing(trade_size_pct, max_position_pct)
    validate_option_settings(
        config.option_type,
        config.target_delta_min,
        config.target_delta_max,
        config.option_min_dte,
        config.option_max_dte,
        config.iv_rank_min,
        config.iv_rank_max,
    )
    symbols = (
        resolve_trade_symbols(config.trade_universes) if config.trade_universes is not None else default_trade_symbols()
    )

    book_repo = BookRepository(conn)
    book_id = book_repo.insert(
        account_id=account_id,
        name="default",
        is_default=1,
        start_equity=float(initial_cash),
        current_cash=float(initial_cash),
        current_equity=float(initial_cash),
        trade_symbols=dumps_json_column(symbols),
        created_at=now_iso,
        updated_at=now_iso,
    )
    sync_default_book_assignment(conn, account_id=account_id, strategy_name=strategy, now_iso=now_iso)
    book_repo.update_settings(
        book_id=book_id,
        updated_at=now_iso,
        settings=BookSettingsUpdate(
            learning_enabled=int(config.learning_enabled if config.learning_enabled is not None else False),
            risk_policy=risk,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            trade_size_pct=trade_size_pct,
            max_position_pct=max_position_pct,
            instrument_mode=mode,
            option_profit_take_pct=config.option_profit_take_pct,
            option_max_loss_pct=config.option_max_loss_pct,
            option_strike_offset_pct=config.option_strike_offset_pct,
            option_min_dte=config.option_min_dte,
            option_max_dte=config.option_max_dte,
            option_type=normalize_option_type(config.option_type) if config.option_type else None,
            target_delta_min=config.target_delta_min,
            target_delta_max=config.target_delta_max,
            max_premium_per_trade=config.max_premium_per_trade,
            max_contracts_per_trade=config.max_contracts_per_trade,
            iv_rank_min=config.iv_rank_min,
            iv_rank_max=config.iv_rank_max,
            roll_dte_threshold=config.roll_dte_threshold,
            goal_min_return_pct=config.goal_min_return_pct,
            goal_max_return_pct=config.goal_max_return_pct,
            goal_period=normalize_lower(config.goal_period or "monthly"),
        ),
    )
