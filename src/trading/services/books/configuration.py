"""Read and edit book-owned operator configuration."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from common.coercion import expect_float, expect_int
from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models.accounts.account_config import AccountConfig
from trading.models.books.book_record import BookRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository
from trading.repositories.unit_of_work import unit_of_work
from trading.services.accounts.config import (
    normalize_instrument_mode,
    normalize_lower,
    normalize_option_type,
    normalize_risk_policy,
    validate_goal_range_from_inputs,
    validate_option_settings_from_inputs,
    validate_position_sizing_from_inputs,
)
from trading.services.books.book_assignments import (
    assign_book_strategy,
    open_assignment_for_book,
)
from trading.services.books.rotation.engine import (
    BookRotationScheduleConfig,
    RotationPolicyConfig,
)
from trading.services.parameters.mutations import (
    update_book_rotation_policy,
    update_book_rotation_scheduling,
)


@dataclass(frozen=True, slots=True)
class BookConfigurationView:
    book: BookRecord
    strategy: str
    rotation_enabled: bool
    rotation_schedule: tuple[str, ...]
    rotation_lookback_days: int
    rotation_policy: RotationPolicyConfig


def _require_account_and_book(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str,
) -> BookRecord:
    account = AccountRepository(conn).fetch_by_name(account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")
    for book in BookRepository(conn).fetch_for_account(account_id=account.id):
        if book.name == book_name:
            return book
    raise NotFoundError(f"Book not found for account {account_name}: {book_name}")


def _parse_schedule(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    parsed = json.loads(raw)
    return tuple(str(value) for value in parsed) if isinstance(parsed, list) else ()


def _view(conn: sqlite3.Connection, book: BookRecord) -> BookConfigurationView:
    assignment = open_assignment_for_book(conn, book_id=book.id)
    rotation = BookRotationSettingsRepository(conn).fetch(book_id=book.id)
    schedule_defaults = BookRotationScheduleConfig()
    policy_defaults = RotationPolicyConfig()
    return BookConfigurationView(
        book=book,
        strategy=assignment.strategy_name if assignment is not None else "unassigned",
        rotation_enabled=(
            bool(rotation.rotation_enabled) if rotation is not None else schedule_defaults.rotation_enabled
        ),
        rotation_schedule=_parse_schedule(rotation.rotation_schedule if rotation is not None else None),
        rotation_lookback_days=(
            rotation.rotation_lookback_days
            if rotation is not None and rotation.rotation_lookback_days is not None
            else schedule_defaults.lookback_days
        ),
        rotation_policy=RotationPolicyConfig(
            **{
                name: (
                    getattr(rotation, name)
                    if rotation is not None and getattr(rotation, name) is not None
                    else getattr(policy_defaults, name)
                )
                for name in (
                    "min_trades_in_window",
                    "outperformance_threshold_bps",
                    "cooldown_days",
                    "risk_adjusted_return_weight",
                    "stability_weight",
                    "drawdown_penalty_weight",
                    "cost_penalty_weight",
                    "regime_fit_weight",
                )
            }
        ),
    )


def fetch_account_book_configurations(
    conn: sqlite3.Connection,
    *,
    account_name: str,
) -> tuple[BookConfigurationView, ...]:
    account = AccountRepository(conn).fetch_by_name(account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")
    return tuple(_view(conn, book) for book in BookRepository(conn).fetch_for_account(account_id=account.id))


def configure_book(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str,
    strategy: str | None,
    config: AccountConfig,
    config_values: dict[str, object],
    rotation_scheduling: dict[str, object],
    rotation_policy: dict[str, int | float | None],
) -> None:
    """Apply a partial, validated edit to one explicitly named book."""
    with unit_of_work(conn):
        book = _require_account_and_book(conn, account_name=account_name, book_name=book_name)
        validate_goal_range_from_inputs(book, config.goal_min_return_pct, config.goal_max_return_pct)
        validate_position_sizing_from_inputs(
            book.trade_size_pct,
            book.max_position_pct,
            config.trade_size_pct,
            config.max_position_pct,
        )
        validate_option_settings_from_inputs(
            book,
            config.option_type,
            config.target_delta_min,
            config.target_delta_max,
            config.option_min_dte,
            config.option_max_dte,
            config.iv_rank_min,
            config.iv_rank_max,
        )

        if strategy is not None:
            if not strategy.strip():
                raise ValidationError("strategy cannot be empty.")
            assign_book_strategy(conn, book_id=book.id, strategy_name=strategy, now_iso=utc_now_iso())

        values: dict[str, object | None] = {
            "learning_enabled": expect_int(config.learning_enabled) if config.learning_enabled is not None else None,
            "risk_policy": normalize_risk_policy(config.risk_policy) if config.risk_policy is not None else None,
            "stop_loss_pct": expect_float(config.stop_loss_pct) if config.stop_loss_pct is not None else None,
            "take_profit_pct": expect_float(config.take_profit_pct) if config.take_profit_pct is not None else None,
            "trade_size_pct": expect_float(config.trade_size_pct) if config.trade_size_pct is not None else None,
            "max_position_pct": expect_float(config.max_position_pct) if config.max_position_pct is not None else None,
            "instrument_mode": (
                normalize_instrument_mode(config.instrument_mode) if config.instrument_mode is not None else None
            ),
            "goal_min_return_pct": (
                expect_float(config.goal_min_return_pct) if config.goal_min_return_pct is not None else None
            ),
            "goal_max_return_pct": (
                expect_float(config.goal_max_return_pct) if config.goal_max_return_pct is not None else None
            ),
            "goal_period": normalize_lower(config.goal_period) if config.goal_period is not None else None,
            "max_trades_per_run": config_values.get("max_trades_per_run"),
        }
        for name in (
            "option_strike_offset_pct",
            "option_min_dte",
            "option_max_dte",
            "target_delta_min",
            "target_delta_max",
            "max_premium_per_trade",
            "max_contracts_per_trade",
            "iv_rank_min",
            "iv_rank_max",
            "roll_dte_threshold",
            "option_profit_take_pct",
            "option_max_loss_pct",
        ):
            if name in config_values:
                values[name] = config_values[name]
        if config.option_type is not None:
            values["option_type"] = normalize_option_type(config.option_type)

        updates = [f"{name} = ?" for name, value in values.items() if value is not None]
        params = [value for value in values.values() if value is not None]
        if updates:
            BookRepository(conn).update_settings_columns(book_id=book.id, updates=updates, params=params)
        if config.trade_universes is not None:
            if not config.trade_universes:
                raise ValidationError("trade_universes must name at least one universe.")
            BookRepository(conn).update_trade_universes(
                book_id=book.id,
                trade_universes=json.dumps(config.trade_universes, separators=(",", ":")),
                updated_at=utc_now_iso(),
            )
        if rotation_scheduling:
            update_book_rotation_scheduling(
                conn,
                account_name=account_name,
                book_name=book_name,
                updates=rotation_scheduling,
            )
        if rotation_policy:
            update_book_rotation_policy(
                conn,
                account_name=account_name,
                book_name=book_name,
                updates=rotation_policy,
            )
