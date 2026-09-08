"""Read and edit book-owned operator configuration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.json_columns import dumps_json_column
from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models.accounts import AccountConfig
from trading.models.books import BookRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.services.books.book_assignments import (
    assign_book_strategy,
    open_assignment_for_book,
)
from trading.services.books.default_book import fetch_account_book
from trading.services.books.rotation.engine import (
    DEFAULT_ROLLING_WINDOW_DAYS,
    RotationPolicyConfig,
    resolve_book_rotation_schedule,
    resolve_rotation_policy_config,
    write_book_rotation_policy,
    write_book_rotation_scheduling,
)
from trading.services.books.settings_validation import (
    book_settings_update_from_config,
    validate_goal_range_from_inputs,
    validate_option_settings_from_inputs,
    validate_position_sizing_from_inputs,
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


def _view(conn: sqlite3.Connection, book: BookRecord) -> BookConfigurationView:
    assignment = open_assignment_for_book(conn, book_id=book.id)
    # The engine resolvers own the NULL-fallback for both scheduling and policy,
    # so the display reads the same effective settings a rotation run would.
    schedule = resolve_book_rotation_schedule(conn, book_id=book.id)
    policy = resolve_rotation_policy_config(conn, book_id=book.id, rolling_window_days=DEFAULT_ROLLING_WINDOW_DAYS)
    return BookConfigurationView(
        book=book,
        strategy=assignment.strategy_name if assignment is not None else "unassigned",
        rotation_enabled=schedule.rotation_enabled,
        rotation_schedule=schedule.schedule,
        rotation_lookback_days=schedule.lookback_days,
        rotation_policy=policy,
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


def apply_book_config(conn: sqlite3.Connection, *, book: BookRecord, config: AccountConfig) -> None:
    """Validate a partial config against ``book`` and write its settings and universe.

    The shared core of the account-level edit and the explicit-book edit: goal,
    sizing, and option inputs are validated merged over the book's current
    values, then the coerced settings (and any universe change) are written to
    the book. Strategy assignment and rotation edits stay caller-specific.
    """
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
    BookRepository(conn).update_settings(
        book_id=book.id,
        settings=book_settings_update_from_config(config),
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


def configure_book(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str,
    strategy: str | None,
    config: AccountConfig,
    rotation_scheduling: dict[str, object],
    rotation_policy: dict[str, int | float | None],
) -> None:
    """Apply a partial, validated edit to one explicitly named book."""
    with unit_of_work(conn):
        book = fetch_account_book(conn, account_name=account_name, book_name=book_name)
        apply_book_config(conn, book=book, config=config)
        if strategy is not None:
            if not strategy.strip():
                raise ValidationError("strategy cannot be empty.")
            assign_book_strategy(conn, book_id=book.id, strategy_name=strategy, now_iso=utc_now_iso())
        if rotation_scheduling:
            write_book_rotation_scheduling(conn, book_id=book.id, updates=rotation_scheduling)
        if rotation_policy:
            write_book_rotation_policy(conn, book_id=book.id, updates=rotation_policy)
