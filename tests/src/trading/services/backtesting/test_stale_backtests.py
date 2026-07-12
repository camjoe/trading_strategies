from __future__ import annotations

import sqlite3

from tests.support.books import set_test_book_rotation_scheduling
from tests.support.evaluation import insert_backtest_run
from tests.support.repositories import insert_repository_account
from trading.repositories.book_bridge import default_book_id
from trading.services.backtesting import find_stale_backtests
from trading.services.books.book_assignments import sync_default_book_assignment

REFERENCE = "2026-03-16T00:00:00Z"


def _seed_run(conn, *, account_id: int, strategy_name: str, created_at: str) -> None:
    run_id = insert_backtest_run(conn, account_id=account_id, strategy_name=strategy_name)
    conn.execute("UPDATE backtest_runs SET created_at = ? WHERE id = ?", (created_at, run_id))
    conn.commit()


def _rotation_account(conn, name: str, *, schedule: list[str], enabled: int = 1) -> int:
    account_id = insert_repository_account(conn, name=name, strategy="trend")
    sync_default_book_assignment(conn, account_id=account_id, strategy_name="trend", now_iso=REFERENCE)
    set_test_book_rotation_scheduling(
        conn, book_id=default_book_id(conn, account_id), enabled=enabled, schedule=schedule
    )
    return account_id


def test_targets_missing_and_stale_across_incumbent_and_challengers(conn: sqlite3.Connection) -> None:
    account_id = _rotation_account(conn, "acct_stale", schedule=["trend", "meanrev", "breakout"])
    # trend (incumbent): fresh; meanrev: stale; breakout: no backtest at all.
    _seed_run(conn, account_id=account_id, strategy_name="trend", created_at="2026-03-15T00:00:00Z")
    _seed_run(conn, account_id=account_id, strategy_name="meanrev", created_at="2026-03-08T00:00:00Z")

    targets = find_stale_backtests(conn, reference_iso=REFERENCE)

    by_strategy = {t.strategy_name: t for t in targets}
    assert set(by_strategy) == {"meanrev", "breakout"}  # trend is fresh → not targeted
    assert by_strategy["meanrev"].reason == "stale"
    assert by_strategy["meanrev"].age_days == 8.0
    assert by_strategy["breakout"].reason == "missing"
    assert by_strategy["breakout"].age_days is None
    assert all(t.account_name == "acct_stale" and t.account_id == account_id for t in targets)


def test_challengers_skipped_when_rotation_disabled(conn: sqlite3.Connection) -> None:
    # Rotation off: only the incumbent's backtest matters.
    account_id = _rotation_account(conn, "acct_off", schedule=["trend", "meanrev"], enabled=0)

    targets = find_stale_backtests(conn, reference_iso=REFERENCE)

    assert [t.strategy_name for t in targets] == ["trend"]
    assert targets[0].reason == "missing"


def test_incumbent_in_schedule_is_deduplicated(conn: sqlite3.Connection) -> None:
    account_id = _rotation_account(conn, "acct_dedup", schedule=["trend", "trend", "meanrev"])
    _seed_run(conn, account_id=account_id, strategy_name="trend", created_at="2026-03-15T00:00:00Z")
    _seed_run(conn, account_id=account_id, strategy_name="meanrev", created_at="2026-03-15T00:00:00Z")

    # Everything fresh → no targets, and trend was only evaluated once.
    assert find_stale_backtests(conn, reference_iso=REFERENCE) == []


def test_account_name_filter(conn: sqlite3.Connection) -> None:
    _rotation_account(conn, "acct_a", schedule=["trend"])
    _rotation_account(conn, "acct_b", schedule=["trend"])

    targets = find_stale_backtests(conn, reference_iso=REFERENCE, account_name="acct_b")

    assert {t.account_name for t in targets} == {"acct_b"}


def test_threshold_override_changes_targets(conn: sqlite3.Connection) -> None:
    account_id = _rotation_account(conn, "acct_thresh", schedule=["trend"])
    # 2 days old: stale under a 1-day threshold, fresh under the default 3-day.
    _seed_run(conn, account_id=account_id, strategy_name="trend", created_at="2026-03-14T00:00:00Z")

    assert find_stale_backtests(conn, reference_iso=REFERENCE) == []
    stale = find_stale_backtests(conn, reference_iso=REFERENCE, threshold_days=1)
    assert [t.reason for t in stale] == ["stale"]
