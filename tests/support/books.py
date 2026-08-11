from __future__ import annotations

from types import SimpleNamespace

from tests.support.repositories import insert_repository_account
from trading.domain.rotation.schedule import dump_rotation_schedule
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.books.book_assignments import assign_book_strategy

DEFAULT_BOOK_TIMESTAMP = "2026-05-03T00:00:00Z"
_BOOTSTRAP_TIMESTAMP = "2026-01-01T00:00:00Z"


def ensure_default_book_id(conn, account_id: int, *, now: str = _BOOTSTRAP_TIMESTAMP) -> int:
    """Return the account's default book id, creating one funded from the account when missing.

    Production creates the default book in ``create_account``; this covers
    fixtures that raw-insert an account row instead. Balances come from
    ``accounts.initial_cash``, so replayed trade history has cash to spend.
    """
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
        (int(account_id),),
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, status, is_default, start_equity, current_cash, current_equity,
            trade_symbols, created_at, updated_at
        )
        SELECT id, 'default', 'active', 1, initial_cash, initial_cash, initial_cash,
               '["AAPL","MSFT"]', ?, ?
        FROM accounts WHERE id = ?
        """,
        (now, now, int(account_id)),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"Account {account_id} does not exist; cannot create its default book.")
    return int(cursor.lastrowid)


def insert_test_book(
    conn,
    *,
    account_id: int,
    name: str = "core",
    status: str = "active",
    start_equity: float = 10_000.0,
    current_cash: float | None = None,
    current_equity: float | None = None,
    created_at: str = DEFAULT_BOOK_TIMESTAMP,
    updated_at: str = DEFAULT_BOOK_TIMESTAMP,
) -> int:
    """Insert a non-default trading book (the successor of the test book)."""
    resolved_cash = start_equity if current_cash is None else current_cash
    resolved_equity = start_equity if current_equity is None else current_equity
    book_id = BookRepository(conn).insert(
        account_id=account_id,
        name=name,
        is_default=0,
        start_equity=start_equity,
        current_cash=resolved_cash,
        current_equity=resolved_equity,
        created_at=created_at,
        updated_at=updated_at,
    )
    if status != "active":
        BookRepository(conn).update_status(book_id=book_id, status=status, updated_at=updated_at)
    return book_id


def assign_test_book_strategy(
    conn,
    *,
    book_id: int,
    strategy_name: str,
    now_iso: str = DEFAULT_BOOK_TIMESTAMP,
) -> None:
    assign_book_strategy(
        conn,
        book_id=book_id,
        strategy_name=strategy_name,
        now_iso=now_iso,
    )


def set_test_book_rotation_scheduling(
    conn,
    *,
    book_id: int,
    enabled: int = 1,
    schedule: list[str] | None = None,
    lookback_days: int | None = None,
    now_iso: str = DEFAULT_BOOK_TIMESTAMP,
) -> None:
    """Write the book's rotation-scheduling row (book-owned since ADR 014)."""
    BookRotationSettingsRepository(conn).upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=enabled,
        rotation_lookback_days=lookback_days,
        rotation_schedule=dump_rotation_schedule(schedule) if schedule is not None else None,
        created_at=now_iso,
        updated_at=now_iso,
    )


def build_book_env(
    conn,
    *,
    account_name: str = "acct_book",
    start_equity: float = 1_000.0,
    snapshot_time: str = "2026-05-03T13:59:00Z",
) -> SimpleNamespace:
    """Create an account + active book + matching snapshot.

    Returns a SimpleNamespace with ``account_name``, ``account_id``, ``book_id``.
    """
    account_id = insert_repository_account(conn, name=account_name)
    book_id = insert_test_book(conn, account_id=account_id, start_equity=start_equity)
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=snapshot_time,
        cash=start_equity,
        market_value=0.0,
        equity=start_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    return SimpleNamespace(account_name=account_name, account_id=account_id, book_id=book_id)


def build_rotation_book_env(
    conn,
    *,
    account_name: str = "acct_book",
    start_equity: float = 1_000.0,
    snapshot_time: str = "2026-05-03T13:59:00Z",
    rotation_strategies: list[str] | None = None,
) -> SimpleNamespace:
    """Create a full rotation-ready book environment.

    Account with rotation schedule, book, incumbent strategy assignment, two
    metric rows, and a matching snapshot. Returns a SimpleNamespace with
    ``account_name``, ``account_id``, ``book_id``.
    """
    if rotation_strategies is None:
        rotation_strategies = ["trend", "meanrev"]

    account_id = insert_repository_account(conn, name=account_name)

    book_id = insert_test_book(conn, account_id=account_id, start_equity=start_equity)
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    # Rotation scheduling is book-owned (ADR 014).
    set_test_book_rotation_scheduling(
        conn,
        book_id=book_id,
        enabled=1,
        schedule=rotation_strategies,
        lookback_days=30,
    )

    # Two metric rows for rotation scoring
    for metric_date, created_at in [("2026-05-03", "2026-05-03T23:59:00Z"), ("2026-05-04", "2026-05-04T23:59:00Z")]:
        DailyMetricsRepository(conn).upsert(
            book_id=book_id,
            metric_date=metric_date,
            return_pct=0.5,
            drawdown_pct=-0.7,
            turnover_pct=2.0,
            slippage_bps=8.0,
            hit_rate=0.45,
            expectancy=0.08,
            risk_adjusted_score=0.60,
            trade_count=10,
            fees_total=3.0,
            created_at=created_at,
            updated_at=created_at,
        )

    EquitySnapshotRepository(conn).insert_for_book(
        book_id=book_id,
        snapshot_time=snapshot_time,
        cash=start_equity,
        market_value=0.0,
        equity=start_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    return SimpleNamespace(account_name=account_name, account_id=account_id, book_id=book_id)


__all__ = [
    "ensure_default_book_id",
    "insert_test_book",
    "assign_test_book_strategy",
    "set_test_book_rotation_scheduling",
    "build_book_env",
    "build_rotation_book_env",
]
