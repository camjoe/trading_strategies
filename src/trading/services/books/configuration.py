"""Read and edit book-owned operator configuration."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace

from common.coercion import expect_int
from common.json_columns import dumps_json_column
from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models.accounts import AccountConfig
from trading.models.books import BookRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository
from trading.services.accounts.validation import (
    book_settings_update_from_config,
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
    ROTATION_POLICY_FIELDS,
    update_book_rotation_policy,
    update_book_rotation_scheduling,
)
from trading.services.universe import resolve_trade_symbols


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
    account = AccountRepository(conn).fetch_by_name(account_name=account_name)
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
                # The edit surface's field list is the single source of truth, so a
                # dropped policy knob cannot leave a stale name behind here.
                for name in ROTATION_POLICY_FIELDS
            }
        ),
    )


def fetch_account_book_configurations(
    conn: sqlite3.Connection,
    *,
    account_name: str,
) -> tuple[BookConfigurationView, ...]:
    account = AccountRepository(conn).fetch_by_name(account_name=account_name)
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

        # Every execution/goal/option column rides on the coerced config, like
        # the account-level edit. Only max_trades_per_run is absent from
        # AccountConfig, so it is overlaid from the raw request payload.
        raw_max_trades = config_values.get("max_trades_per_run")
        settings = replace(
            book_settings_update_from_config(config),
            max_trades_per_run=expect_int(raw_max_trades) if raw_max_trades is not None else None,
        )
        BookRepository(conn).update_settings(
            book_id=book.id,
            settings=settings,
            updated_at=utc_now_iso(),
        )
        if config.trade_universes is not None:
            # Names are shorthand; the book stores the expansion (revision 0029).
            symbols = resolve_trade_symbols(config.trade_universes)
            BookRepository(conn).update_trade_symbols(
                book_id=book.id,
                trade_symbols=dumps_json_column(symbols),
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
