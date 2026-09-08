"""Revision 0031: client_order_id, the pending status, and the order_fills carry.

The carry is the reason this file exists. Rebuilding ``orders`` drops it, and
``order_fills.order_id`` cascades on delete, so a rebuild that does not preserve
the fills destroys the system's only execution history — silently, since
``PRAGMA foreign_key_check`` reports nothing afterwards.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from infrastructure.database import migration_runner


def _seed_order_with_fill(conn: sqlite3.Connection, *, status: str = "filled") -> None:
    conn.execute("INSERT INTO accounts (name, initial_cash, created_at, updated_at) VALUES ('a', 1, 't', 't')")
    conn.execute(
        """
        INSERT INTO books (account_id, name, is_default, start_equity, current_cash,
                           current_equity, trade_symbols, created_at, updated_at)
        VALUES (1, 'd', 1, 1, 1, 1, '[]', 't', 't')
        """
    )
    conn.execute(
        """
        INSERT INTO orders (book_id, account_id, symbol, side, qty, status, submitted_at, updated_at)
        VALUES (1, 1, 'AAPL', 'buy', 1, ?, 't', 't')
        """,
        (status,),
    )
    conn.execute(
        """
        INSERT INTO order_fills (order_id, exec_id, filled_qty, fill_price, commission, fill_time)
        VALUES (1, 'e1', 1, 100.0, 0.0, 't')
        """,
    )
    conn.commit()


@pytest.fixture
def conn_at_0030(tmp_path: Path) -> Any:
    """A populated database one revision below 0031, with FKs enforced as in production."""
    conn = sqlite3.connect(tmp_path / "revision_0031.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migration_runner.upgrade("0030", connection=conn)
    _seed_order_with_fill(conn)
    try:
        yield conn
    finally:
        conn.close()


def _fill_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM order_fills").fetchone()[0])


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row["name"]) for row in conn.execute("PRAGMA table_info(orders)")}


def test_upgrade_keeps_order_fills(conn_at_0030) -> None:
    assert _fill_count(conn_at_0030) == 1

    migration_runner.upgrade("0031", connection=conn_at_0030)

    assert _fill_count(conn_at_0030) == 1
    fill = conn_at_0030.execute("SELECT * FROM order_fills").fetchone()
    assert (fill["order_id"], fill["exec_id"], fill["fill_price"]) == (1, "e1", 100.0)


def test_upgrade_adds_client_order_id_and_accepts_pending(conn_at_0030) -> None:
    migration_runner.upgrade("0031", connection=conn_at_0030)

    assert "client_order_id" in _columns(conn_at_0030)
    conn_at_0030.execute(
        """
        INSERT INTO orders (book_id, account_id, client_order_id, symbol, side, qty,
                            status, submitted_at, updated_at)
        VALUES (1, 1, 'COID-1', 'MSFT', 'buy', 1, 'pending', 't', 't')
        """
    )
    conn_at_0030.commit()
    row = conn_at_0030.execute("SELECT status, client_order_id FROM orders WHERE symbol = 'MSFT'").fetchone()
    assert (row["status"], row["client_order_id"]) == ("pending", "COID-1")


def test_client_order_id_is_unique_per_account(conn_at_0030) -> None:
    migration_runner.upgrade("0031", connection=conn_at_0030)
    insert = """
        INSERT INTO orders (book_id, account_id, client_order_id, symbol, side, qty,
                            status, submitted_at, updated_at)
        VALUES (1, 1, 'COID-DUP', ?, 'buy', 1, 'pending', 't', 't')
    """
    conn_at_0030.execute(insert, ("MSFT",))

    with pytest.raises(sqlite3.IntegrityError):
        conn_at_0030.execute(insert, ("NVDA",))


def test_downgrade_restores_the_old_shape_and_keeps_fills(conn_at_0030) -> None:
    migration_runner.upgrade("0031", connection=conn_at_0030)
    conn_at_0030.execute(
        """
        INSERT INTO orders (book_id, account_id, client_order_id, symbol, side, qty,
                            status, submitted_at, updated_at)
        VALUES (1, 1, 'COID-2', 'MSFT', 'buy', 1, 'pending', 't', 't')
        """
    )
    conn_at_0030.commit()

    migration_runner.downgrade("0030", connection=conn_at_0030)

    assert "client_order_id" not in _columns(conn_at_0030)
    assert _fill_count(conn_at_0030) == 1
    # The pending row survives as 'submitted' — the closest word the old vocabulary has.
    assert conn_at_0030.execute("SELECT status FROM orders WHERE symbol = 'MSFT'").fetchone()["status"] == "submitted"
