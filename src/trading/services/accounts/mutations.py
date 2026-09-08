from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from trading.domain.exceptions import AccountAlreadyExistsError, NotFoundError, ValidationError
from trading.models import AccountConfig, AccountInsert, AccountRecord
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.services.accounts.queries import find_account, normalize_account_name
from trading.services.books.book_assignments import sync_default_book_assignment
from trading.services.books.configuration import apply_book_config
from trading.services.books.provisioning import bootstrap_default_book


def get_account(conn: sqlite3.Connection, name: str) -> AccountRecord:
    row = find_account(conn, name)
    if row is None:
        raise NotFoundError(f"Account '{name}' not found.")
    return row


def _normalize_benchmark_ticker(benchmark_ticker: str) -> str:
    normalized = benchmark_ticker.upper().strip()
    if not normalized:
        raise ValidationError("benchmark_ticker cannot be empty.")
    return normalized


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
    name = normalize_account_name(name)
    if initial_cash <= 0:
        raise ValidationError("initial_cash must be greater than 0.")
    validate_strategy_name(strategy)

    display = (cfg.descriptive_name or name).strip()
    if not display:
        display = name

    created_ts = utc_now_iso()
    try:
        AccountRepository(conn).insert(
            AccountInsert(
                name=name,
                initial_cash=float(initial_cash),
                created_at=created_ts,
                updated_at=created_ts,
                benchmark_ticker=_normalize_benchmark_ticker(benchmark_ticker),
                descriptive_name=display,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise AccountAlreadyExistsError(f"Account '{name}' already exists.") from exc

    # Books are the execution primitive (ADR 010/014): provision the account's
    # default book so it trades from day one. Runs in the same unit_of_work, so
    # a bad config or universe here rolls the account row back too.
    account = get_account(conn, name)
    bootstrap_default_book(
        conn,
        account_id=account.id,
        strategy=strategy,
        initial_cash=initial_cash,
        config=cfg,
        now_iso=created_ts,
    )


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


def set_benchmark(conn: sqlite3.Connection, account_name: str, benchmark_ticker: str) -> None:
    account = get_account(conn, account_name)
    AccountRepository(conn).update(
        account_id=account.id,
        values={"benchmark_ticker": _normalize_benchmark_ticker(benchmark_ticker)},
        updated_at=utc_now_iso(),
    )


def _configure_account(
    conn: sqlite3.Connection,
    account_name: str,
    config: AccountConfig | None = None,
) -> None:
    cfg = config or AccountConfig()
    account = get_account(conn, account_name)

    display: str | None = None
    if cfg.descriptive_name is not None:
        display = cfg.descriptive_name.strip()
        if not display:
            raise ValidationError("descriptive_name cannot be empty.")

    # Goals, universes, and execution/option knobs are book columns
    # (revisions 0004/0005/0008): the shared book-config edit validates them
    # against the default book's current values, then writes to the book.
    book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
    if book is None:
        raise NotFoundError(f"Default book missing for account id {account.id}.")
    apply_book_config(conn, book=book, config=cfg)

    if display is not None:
        AccountRepository(conn).update(
            account_id=account.id,
            values={"descriptive_name": display},
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
