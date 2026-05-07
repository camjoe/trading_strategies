from __future__ import annotations

import sqlite3


def insert_sleeve_risk_decision(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    sleeve_id: int | None,
    decision_time: str,
    symbol: str | None,
    side: str | None,
    action: str,
    reason_code: str,
    requested_qty: int | None,
    approved_qty: int | None,
    requested_notional: float | None,
    approved_notional: float | None,
    execution_mode: str,
    risk_payload_json: str,
    created_at: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO sleeve_risk_decisions (
            account_id,
            sleeve_id,
            decision_time,
            symbol,
            side,
            action,
            reason_code,
            requested_qty,
            approved_qty,
            requested_notional,
            approved_notional,
            execution_mode,
            risk_payload_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(account_id),
            None if sleeve_id is None else int(sleeve_id),
            decision_time,
            symbol,
            side,
            action,
            reason_code,
            None if requested_qty is None else int(requested_qty),
            None if approved_qty is None else int(approved_qty),
            None if requested_notional is None else float(requested_notional),
            None if approved_notional is None else float(approved_notional),
            execution_mode,
            risk_payload_json,
            created_at,
        ),
    )
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected sleeve_risk_decisions id after insert.")
    return int(cursor.lastrowid)


def fetch_sleeve_risk_decisions_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM sleeve_risk_decisions
        WHERE account_id = ?
        ORDER BY decision_time DESC, id DESC
        LIMIT ?
        """,
        (int(account_id), int(limit)),
    ).fetchall()


def fetch_sleeve_risk_decisions_for_account_date(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    report_date: str,
) -> list[sqlite3.Row]:
    """Return all risk decisions for *account_id* that fall on *report_date* (YYYY-MM-DD)."""
    import datetime as dt

    next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
    return conn.execute(
        """
        SELECT *
        FROM sleeve_risk_decisions
        WHERE account_id = ?
          AND decision_time >= ?
          AND decision_time < ?
        ORDER BY decision_time ASC, id ASC
        """,
        (int(account_id), report_date, next_date),
    ).fetchall()
