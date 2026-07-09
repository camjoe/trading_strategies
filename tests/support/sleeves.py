from __future__ import annotations

from types import SimpleNamespace

from trading.domain.rotation import dump_rotation_schedule
from trading.repositories.books import BookRepository
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.sleeves.book_assignments import assign_book_strategy
from tests.support.repositories import insert_repository_account

DEFAULT_BOOK_TIMESTAMP = "2026-05-03T00:00:00Z"


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
    """Insert a non-default trading book (the successor of the test sleeve)."""
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
    param_set_id: int | None = None,
    now_iso: str = DEFAULT_BOOK_TIMESTAMP,
) -> None:
    assign_book_strategy(
        conn,
        book_id=book_id,
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        now_iso=now_iso,
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
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
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

    account_id = insert_repository_account(conn, name=account_name, strategy="trend")
    conn.execute(
        "UPDATE accounts SET rotation_schedule = ?, rotation_lookback_days = ? WHERE id = ?",
        (dump_rotation_schedule(rotation_strategies), 30, account_id),
    )
    conn.commit()

    book_id = insert_test_book(conn, account_id=account_id, start_equity=start_equity)
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")

    # Two metric rows for rotation scoring
    for metric_date, created_at in [("2026-05-03", "2026-05-03T23:59:00Z"), ("2026-05-04", "2026-05-04T23:59:00Z")]:
        DailyMetricsRepository(conn).upsert(
            account_id=account_id,
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

    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=start_equity,
        market_value=0.0,
        equity=start_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    return SimpleNamespace(account_name=account_name, account_id=account_id, book_id=book_id)


__all__ = [
    "insert_test_book",
    "assign_test_book_strategy",
    "build_book_env",
    "build_rotation_book_env",
]
