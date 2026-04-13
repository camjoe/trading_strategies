from __future__ import annotations

import sqlite3


def fetch_recent_equity_rows(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT equity
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT ?
        """,
        (account_id, int(limit)),
    ).fetchall()


def insert_snapshot_row(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl,
        ),
    )
    conn.commit()


def fetch_snapshot_history_rows(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT ?
        """,
        (account_id, int(limit)),
    ).fetchall()


def fetch_snapshot_count_between(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    start_iso: str,
    end_iso: str,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS snapshot_count
        FROM equity_snapshots
        WHERE account_id = ?
          AND snapshot_time >= ?
          AND snapshot_time <= ?
        """,
        (int(account_id), start_iso, end_iso),
    ).fetchone()
    return int(row["snapshot_count"]) if row is not None else 0


def fetch_snapshot_count_for_account(conn: sqlite3.Connection, *, account_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS snapshot_count
        FROM equity_snapshots
        WHERE account_id = ?
        """,
        (int(account_id),),
    ).fetchone()
    return int(row["snapshot_count"]) if row is not None else 0


def fetch_latest_snapshot_row(conn: sqlite3.Connection, *, account_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT snapshot_time, equity
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        """,
        (int(account_id),),
    ).fetchone()


def fetch_latest_snapshot_details_row(conn: sqlite3.Connection, *, account_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM equity_snapshots
        WHERE account_id = ?
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        """,
        (int(account_id),),
    ).fetchone()
