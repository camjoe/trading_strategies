from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.database.backend import SQLiteBackend, get_backend, set_backend
from infrastructure.database.connection import ensure_db
from tests.support.db_schema import build_db_at_head
from trading.domain.strategy_signals import PRIMITIVE_CATALOG
from trading.repositories.strategies import StrategyRepository
from trading.repositories.books import BookRepository
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_settings import (
    BookRotationSettingsRepository,
)
from trading.services.strategy_catalog import ensure_default_books, seed_strategy_catalog

NOW = "2026-07-03T12:00:00Z"


@pytest.fixture
def conn(tmp_path: Path):
    original = get_backend()
    set_backend(SQLiteBackend(build_db_at_head(tmp_path / "paper_trading.db")))
    connection = ensure_db()
    try:
        yield connection
    finally:
        connection.close()
        set_backend(original)


def test_seed_strategy_catalog_creates_all_primitives_idempotently(conn) -> None:
    inserted = seed_strategy_catalog(conn, now_iso=NOW)
    assert inserted == len(PRIMITIVE_CATALOG)

    # Idempotent: nothing added on re-run.
    assert seed_strategy_catalog(conn, now_iso=NOW) == 0

    repo = StrategyRepository(conn)
    trend = repo.fetch_by_key(strategy_key="trend")
    assert trend is not None
    assert trend.primitive == "trend"
    assert trend.status == "draft"
    assert json.loads(trend.params_json) == dict(PRIMITIVE_CATALOG["trend"].knob_schema)
    assert trend.style == PRIMITIVE_CATALOG["trend"].style

    news = repo.fetch_by_key(strategy_key="news_sentiment")
    assert news is not None
    assert news.style == "alternative"
    assert news.required_features is not None
    assert json.loads(news.required_features) == list(PRIMITIVE_CATALOG["news_sentiment"].required_features)


def test_ensure_default_books_bootstraps_book_settings_and_assignment(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES ('acct_seed', 'trend', 5000, ?)",
        (NOW,),
    )
    conn.execute(
        """
        UPDATE accounts
        SET goal_min_return_pct = 2.0, trade_universes = '["core"]'
        WHERE name = 'acct_seed'
        """
    )
    conn.commit()
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'acct_seed'").fetchone()[0])

    created = ensure_default_books(conn, now_iso=NOW)
    assert created == 1
    assert ensure_default_books(conn, now_iso=NOW) == 0  # idempotent

    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    assert book is not None
    assert book.is_default == 1
    assert book.start_equity == pytest.approx(5000.0)
    assert book.goal_min_return_pct == pytest.approx(2.0)
    assert book.trade_universes == '["core"]'

    # Execution settings are book columns (revision 0004); bootstrap starts on
    # DDL defaults — account creation / editors set real values.
    assert book.risk_policy == "none"
    assert book.stop_loss_pct is None
    assert book.learning_enabled == 0

    rotation = BookRotationSettingsRepository(conn).fetch(book_id=book.id)
    assert rotation is not None
    # Account rotation columns are gone (revision 0003): bootstrapped books
    # start with rotation disabled until profiles/settings enable it.
    assert rotation.rotation_enabled == 0
    trend_id = StrategyRepository(conn).fetch_by_key(strategy_key="trend")
    assert trend_id is not None

    assignment = BookAssignmentRepository(conn).fetch_open(book_id=book.id)
    assert assignment is not None
    assert assignment.strategy_id == trend_id.id


def test_ensure_default_books_skips_unknown_legacy_strategy_label(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, strategy, initial_cash, created_at) VALUES ('acct_odd', 'Momentum Growth X', 1000, ?)",
        (NOW,),
    )
    conn.commit()
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'acct_odd'").fetchone()[0])

    assert ensure_default_books(conn, now_iso=NOW) == 1
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    assert book is not None
    # Unknown label → no assignment opened; book still bootstrapped.
    assert BookAssignmentRepository(conn).fetch_open(book_id=book.id) is None
