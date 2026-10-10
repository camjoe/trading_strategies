from __future__ import annotations

import sqlite3
from decimal import Decimal

from scripts.data_ops.check_cash_invariant import invariant_payload
from tests.support.books import ensure_default_book_id
from tests.support.db_schema import memory_db_at_head
from trading.persistence.money_columns import encode_money


def _seed_account_with_default_book(conn: sqlite3.Connection, *, name: str, initial_cash: float) -> int:
    conn.execute(
        "INSERT INTO accounts (name, initial_cash, created_at, updated_at) "
        "VALUES (?, ?, '2026-07-17T00:00:00Z', '2026-07-17T00:00:00Z')",
        (name, encode_money(Decimal(str(initial_cash)))),
    )
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()["id"])
    return ensure_default_book_id(conn, account_id)


def _insert_ledger(conn: sqlite3.Connection, *, book_id: int, entry_type: str, amount: float) -> None:
    conn.execute(
        """
        INSERT INTO ledger (book_id, entry_type, amount, entry_time, created_at)
        VALUES (?, ?, ?, '2026-07-17T00:00:00Z', '2026-07-17T00:00:00Z')
        """,
        (book_id, entry_type, encode_money(Decimal(str(amount)))),
    )


def _set_current_cash(conn: sqlite3.Connection, *, book_id: int, amount: float) -> None:
    conn.execute("UPDATE books SET current_cash = ? WHERE id = ?", (encode_money(Decimal(str(amount))), book_id))


def test_reconciled_books_pass() -> None:
    conn = memory_db_at_head()
    try:
        book_id = _seed_account_with_default_book(conn, name="clean", initial_cash=1000.0)
        # A fill's trade + fee entries, applied to cash exactly.
        _insert_ledger(conn, book_id=book_id, entry_type="trade", amount=-500.0)
        _insert_ledger(conn, book_id=book_id, entry_type="fee", amount=-1.0)
        _set_current_cash(conn, book_id=book_id, amount=499.0)

        payload = invariant_payload(conn)
    finally:
        conn.close()

    assert len(payload["books"]) == 1
    assert payload["books"][0]["ok"] is True
    assert payload["divergent"] == []


def test_any_drift_is_flagged() -> None:
    # Money is exact integer minor units, so even a sub-cent drift is a divergence.
    conn = memory_db_at_head()
    try:
        book_id = _seed_account_with_default_book(conn, name="drifted", initial_cash=1000.0)
        _insert_ledger(conn, book_id=book_id, entry_type="deposit", amount=250.0)
        _set_current_cash(conn, book_id=book_id, amount=1250.05)

        payload = invariant_payload(conn)
    finally:
        conn.close()

    assert len(payload["divergent"]) == 1
    flagged = payload["divergent"][0]
    assert flagged["book_id"] == book_id
    assert flagged["account_name"] == "drifted"
    assert flagged["ledger_sum"] == 250.0
    assert abs(flagged["divergence"] - 0.05) < 1e-9


def test_book_with_no_ledger_rows_uses_zero_sum() -> None:
    conn = memory_db_at_head()
    try:
        _seed_account_with_default_book(conn, name="untouched", initial_cash=500.0)

        payload = invariant_payload(conn)
    finally:
        conn.close()

    assert len(payload["books"]) == 1
    assert payload["books"][0]["ledger_sum"] == 0.0
    assert payload["divergent"] == []
