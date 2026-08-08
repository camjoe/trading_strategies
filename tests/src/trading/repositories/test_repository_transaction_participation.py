"""Repository writes must participate in an enclosing ``unit_of_work`` scope.

``test_unit_of_work.py`` covers the primitive itself. These cover the rule it
depends on: a repository write that runs inside an open scope must defer its
commit to that scope, so a later failure rolls it back. Each repository below
previously hard-committed (``conn.commit()``), which silently ended the
transaction early and defeated the rollback guarantee.
"""

from __future__ import annotations

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.persistence.unit_of_work import unit_of_work
from trading.repositories.books import BookRepository
from trading.repositories.global_settings import GlobalSettingsRepository
from trading.repositories.strategies import StrategyRepository

NOW = "2026-07-23T00:00:00Z"


def test_global_settings_upsert_rolls_back_inside_failed_scope(conn) -> None:
    with pytest.raises(RuntimeError):
        with unit_of_work(conn):
            GlobalSettingsRepository(conn).upsert_throttle_settings(
                runtime_max_trades_per_day=7,
                runtime_max_trades_per_minute=2,
                updated_at=NOW,
            )
            raise RuntimeError("boom")

    record = GlobalSettingsRepository(conn).fetch()
    assert record is None or record.runtime_max_trades_per_day != 7


def test_global_settings_upsert_still_persists_standalone(conn) -> None:
    # Outside any scope the write must commit immediately, exactly as before.
    GlobalSettingsRepository(conn).upsert_throttle_settings(
        runtime_max_trades_per_day=9,
        runtime_max_trades_per_minute=3,
        updated_at=NOW,
    )
    conn.rollback()

    record = GlobalSettingsRepository(conn).fetch()
    assert record is not None
    assert record.runtime_max_trades_per_day == 9


def test_strategy_insert_rolls_back_inside_failed_scope(conn) -> None:
    with pytest.raises(RuntimeError):
        with unit_of_work(conn):
            StrategyRepository(conn).insert(
                strategy_key="uow_probe",
                primitive="trend",
                params_json="{}",
                created_at=NOW,
                updated_at=NOW,
            )
            raise RuntimeError("boom")

    row = conn.execute("SELECT COUNT(*) FROM strategies WHERE strategy_key = 'uow_probe'").fetchone()
    assert int(row[0]) == 0


def test_book_status_update_rolls_back_inside_failed_scope(conn) -> None:
    account_id = insert_repository_account(conn, name="uow_book_acct")
    book_id = insert_test_book(conn, account_id=account_id)
    original = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert original is not None
    assert original.status != "paused"

    with pytest.raises(RuntimeError):
        with unit_of_work(conn):
            BookRepository(conn).update_status(book_id=book_id, status="paused", updated_at=NOW)
            raise RuntimeError("boom")

    after = BookRepository(conn).fetch_by_id(book_id=book_id)
    assert after is not None
    assert after.status == original.status
