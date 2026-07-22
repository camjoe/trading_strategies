"""Tests for trading.services.books.rotation.engine.resolve_book_rotation_schedule (ADR 014)."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import insert_test_book, set_test_book_rotation_scheduling
from tests.support.repositories import insert_repository_account
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.books.rotation.engine import (
    DEFAULT_ROLLING_WINDOW_DAYS,
    BookRotationScheduleConfig,
    resolve_book_rotation_schedule,
)


@pytest.fixture
def book_id(conn: sqlite3.Connection) -> int:
    account_id = insert_repository_account(conn, name="sched_acct")
    return insert_test_book(conn, account_id=account_id, name="book_a")


def test_missing_row_means_disabled_defaults(conn: sqlite3.Connection, book_id: int) -> None:
    config = resolve_book_rotation_schedule(conn, book_id=book_id)

    assert config == BookRotationScheduleConfig()
    assert config.rotation_enabled is False
    assert config.schedule == ()
    assert config.lookback_days == DEFAULT_ROLLING_WINDOW_DAYS


def test_row_values_resolve_per_field(conn: sqlite3.Connection, book_id: int) -> None:
    set_test_book_rotation_scheduling(
        conn, book_id=book_id, enabled=1, schedule=["trend", "meanrev"], lookback_days=90
    )

    config = resolve_book_rotation_schedule(conn, book_id=book_id)

    assert config.rotation_enabled is True
    assert config.schedule == ("trend", "meanrev")
    assert config.lookback_days == 90


def test_null_schedule_and_lookback_fall_back(conn: sqlite3.Connection, book_id: int) -> None:
    set_test_book_rotation_scheduling(conn, book_id=book_id, enabled=1, schedule=None, lookback_days=None)

    config = resolve_book_rotation_schedule(conn, book_id=book_id)

    assert config.rotation_enabled is True
    assert config.schedule == ()
    assert config.lookback_days == DEFAULT_ROLLING_WINDOW_DAYS


def test_malformed_schedule_degrades_to_no_challengers(conn: sqlite3.Connection, book_id: int) -> None:
    BookRotationSettingsRepository(conn).upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=1,
        rotation_lookback_days=30,
        rotation_schedule="not-json[",
        created_at="2026-05-03T00:00:00Z",
        updated_at="2026-05-03T00:00:00Z",
    )

    config = resolve_book_rotation_schedule(conn, book_id=book_id)

    assert config.rotation_enabled is True
    assert config.schedule == ()
