"""Edit workflows for the unified parameter source.

Owns the targeted book rotation edits (policy and scheduling): resolve the
account's book, merge the provided fields over the persisted row, and write
it back. Global operational settings edits live in
``trading.services.operational_settings.mutations``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models.books import BookRotationSettingsRecord
from trading.services.books.default_book import fetch_account_book
from trading.services.books.rotation.engine import (
    ROTATION_POLICY_FIELDS,
    write_book_rotation_policy,
    write_book_rotation_scheduling,
)

# The book rotation-scheduling fields the edit command may touch (book-owned,
# ADR 014); None clears schedule/lookback back to the code default.
ROTATION_SCHEDULING_FIELDS = (
    "rotation_enabled",
    "rotation_schedule",
    "rotation_lookback_days",
)


def resolve_book_id(conn: sqlite3.Connection, *, account_name: str, book_name: str | None) -> int:
    return fetch_account_book(conn, account_name=account_name, book_name=book_name).id


def update_book_rotation_policy(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    updates: Mapping[str, int | float | None],
) -> BookRotationSettingsRecord:
    """Merge ``updates`` over the book's persisted rotation policy and save.

    Only keys from ``ROTATION_POLICY_FIELDS`` are accepted; a None value
    clears the field back to the code default. Returns the persisted row.
    """
    unknown = sorted(set(updates) - set(ROTATION_POLICY_FIELDS))
    if unknown:
        raise ValueError(f"Unknown rotation policy fields: {', '.join(unknown)}")
    if not updates:
        raise ValueError("No rotation policy fields provided.")

    book_id = resolve_book_id(conn, account_name=account_name, book_name=book_name)
    return write_book_rotation_policy(conn, book_id=book_id, updates=updates)


def update_book_rotation_scheduling(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    updates: Mapping[str, object],
) -> BookRotationSettingsRecord:
    """Merge ``updates`` over the book's persisted rotation scheduling and save.

    Only keys from ``ROTATION_SCHEDULING_FIELDS`` are accepted.
    ``rotation_schedule`` takes a list of strategy names (validated) or None
    for no challengers; ``rotation_lookback_days`` None falls back to the code
    default. Returns the persisted row.
    """
    unknown = sorted(set(updates) - set(ROTATION_SCHEDULING_FIELDS))
    if unknown:
        raise ValueError(f"Unknown rotation scheduling fields: {', '.join(unknown)}")
    if not updates:
        raise ValueError("No rotation scheduling fields provided.")

    book_id = resolve_book_id(conn, account_name=account_name, book_name=book_name)
    return write_book_rotation_scheduling(conn, book_id=book_id, updates=updates)
