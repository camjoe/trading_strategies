from __future__ import annotations

import json

import pytest

from trading.domain.strategies.registry import PRIMITIVE_CATALOG
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_settings import (
    BookRotationSettingsRepository,
)
from trading.repositories.books import BookRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.strategy_catalog import ensure_default_books, seed_strategy_catalog
from trading.services.universe import default_trade_symbols

NOW = "2026-07-03T12:00:00Z"


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
    # style/required_features are code-owned (PrimitiveSpec), no longer stored on
    # the row (revision 0017); the seeded row carries only variant identity.

    breakout = repo.fetch_by_key(strategy_key="breakout")
    assert breakout is not None
    assert breakout.primitive == "breakout"


def test_ensure_default_books_bootstraps_book_settings_and_assignment(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES ('acct_seed', 5000, ?, ?)",
        (NOW, NOW),
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
    assert json.loads(book.trade_symbols) == default_trade_symbols()

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

    # Repair-path books open with no assignment (accounts.strategy was
    # dropped in revision 0008); operators assign explicitly.
    assignment = BookAssignmentRepository(conn).fetch_open(book_id=book.id)
    assert assignment is None


def test_ensure_default_books_skips_unknown_legacy_strategy_label(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)
    conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES ('acct_odd', 1000, ?, ?)",
        (NOW, NOW),
    )
    conn.commit()
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'acct_odd'").fetchone()[0])

    assert ensure_default_books(conn, now_iso=NOW) == 1
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    assert book is not None
    # Unknown label → no assignment opened; book still bootstrapped.
    assert BookAssignmentRepository(conn).fetch_open(book_id=book.id) is None
