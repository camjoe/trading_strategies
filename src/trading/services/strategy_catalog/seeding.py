"""Seed the catalog tables from code and legacy account config.

Two idempotent bootstrap passes:

- `seed_strategy_catalog` re-creates the code registry's strategies as
  `strategies` rows (primitive + default knobs) so nothing is lost when
  strategies go data.
- `ensure_default_books` gives every account its real default book and copies
  the account's legacy settings columns into the per-concern book settings
  tables so book-keyed reads have data to stand on.
"""

from __future__ import annotations

import json
import sqlite3

from common.coercion import row_expect_float, row_expect_int
from common.time import utc_now_iso
from trading.domain.strategy_signals import PRIMITIVE_CATALOG
from trading.repositories.strategies import StrategyRepository
from trading.repositories.books import BookRepository
from trading.repositories.book_settings import BookRotationSettingsRepository


def seed_strategy_catalog(conn: sqlite3.Connection, *, now_iso: str | None = None) -> int:
    """Insert a strategies row per code primitive that has no row yet; returns rows added."""
    now = now_iso or utc_now_iso()
    repo = StrategyRepository(conn)
    inserted = 0
    for primitive in sorted(PRIMITIVE_CATALOG):
        spec = PRIMITIVE_CATALOG[primitive]
        if repo.fetch_by_key(strategy_key=primitive) is not None:
            continue
        repo.insert(
            strategy_key=primitive,
            primitive=primitive,
            params_json=json.dumps(dict(spec.knob_schema), sort_keys=True),
            style=spec.style,
            required_features=json.dumps(list(spec.required_features)) if spec.required_features else None,
            description=spec.description or None,
            status="draft",
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        inserted += 1
    return inserted


def _seed_book_settings(conn: sqlite3.Connection, *, book_id: int, now: str) -> None:
    # Execution and option settings are books columns (revisions 0004/0005),
    # so a bootstrapped default book starts on DDL defaults; account creation
    # and the book settings editors set real values. Rotation starts disabled
    # (account rotation columns were dropped in 0003; book-owned per ADR 014).
    BookRotationSettingsRepository(conn).upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=0,
        rotation_lookback_days=None,
        rotation_schedule=None,
        created_at=now,
        updated_at=now,
    )


def ensure_default_books(conn: sqlite3.Connection, *, now_iso: str | None = None) -> int:
    """Create the default book + settings rows for accounts missing one.

    Repair path only: accounts carry no strategy/goal/universe columns since
    revision 0008, so a repaired book starts on DDL defaults with the default
    universe and no assignment — the account create path and book editors set
    real values. Returns books created.
    """
    now = now_iso or utc_now_iso()
    book_repo = BookRepository(conn)

    accounts = conn.execute("SELECT * FROM accounts ORDER BY id ASC").fetchall()
    created = 0
    for account in accounts:
        account_id = row_expect_int(dict(account), "id")
        if book_repo.fetch_default_for_account(account_id=account_id) is not None:
            continue
        initial_cash = row_expect_float(dict(account), "initial_cash")
        book_id = book_repo.insert(
            account_id=account_id,
            name="default",
            is_default=1,
            start_equity=initial_cash,
            current_cash=initial_cash,
            current_equity=initial_cash,
            created_at=now,
            updated_at=now,
        )
        _seed_book_settings(conn, book_id=book_id, now=now)
        created += 1
    return created
