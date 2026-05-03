from __future__ import annotations

import sqlite3


def insert_sleeve_ledger_entry(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    entry_type: str,
    amount: float,
    reference_type: str | None,
    reference_id: str | None,
    entry_time: str,
    created_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO sleeve_ledger (
            sleeve_id,
            entry_type,
            amount,
            reference_type,
            reference_id,
            entry_time,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(sleeve_id),
            entry_type,
            float(amount),
            reference_type,
            reference_id,
            entry_time,
            created_at,
        ),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected sleeve_ledger id after insert.")
    return int(cursor.lastrowid)


def fetch_sleeve_ledger_entries(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_ledger
        WHERE sleeve_id = ?
        ORDER BY entry_time DESC, id DESC
        LIMIT ?
        """,
        (int(sleeve_id), int(limit)),
    ).fetchall()


def fetch_sleeve_ledger_sum_by_type(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    entry_type: str,
) -> float:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total_amount
        FROM sleeve_ledger
        WHERE sleeve_id = ? AND entry_type = ?
        """,
        (int(sleeve_id), entry_type),
    ).fetchone()
    if row is None:
        return 0.0
    return float(row["total_amount"])
