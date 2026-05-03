from __future__ import annotations

import sqlite3


def upsert_sleeve_position(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    symbol: str,
    qty: float,
    avg_cost: float,
    market_value: float,
    unrealized_pnl: float,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sleeve_positions (
            sleeve_id,
            symbol,
            qty,
            avg_cost,
            market_value,
            unrealized_pnl,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sleeve_id, symbol)
        DO UPDATE SET
            qty = excluded.qty,
            avg_cost = excluded.avg_cost,
            market_value = excluded.market_value,
            unrealized_pnl = excluded.unrealized_pnl,
            updated_at = excluded.updated_at
        """,
        (
            int(sleeve_id),
            symbol,
            float(qty),
            float(avg_cost),
            float(market_value),
            float(unrealized_pnl),
            updated_at,
        ),
    )
    conn.commit()


def delete_sleeve_position(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    symbol: str,
) -> None:
    conn.execute(
        """
        DELETE FROM sleeve_positions
        WHERE sleeve_id = ? AND symbol = ?
        """,
        (int(sleeve_id), symbol),
    )
    conn.commit()


def fetch_sleeve_position(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    symbol: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_positions
        WHERE sleeve_id = ? AND symbol = ?
        """,
        (int(sleeve_id), symbol),
    ).fetchone()


def fetch_sleeve_positions(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_positions
        WHERE sleeve_id = ?
        ORDER BY symbol ASC
        """,
        (int(sleeve_id),),
    ).fetchall()


def fetch_sleeve_positions_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT p.*
        FROM sleeve_positions p
        JOIN strategy_sleeves s ON s.id = p.sleeve_id
        WHERE s.account_id = ?
        ORDER BY p.sleeve_id ASC, p.symbol ASC
        """,
        (int(account_id),),
    ).fetchall()
