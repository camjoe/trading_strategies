from __future__ import annotations

import datetime as dt
import sqlite3

from trading.models.sleeve_risk_decision_record import SleeveRiskDecisionRecord


class SleeveRiskDecisionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> SleeveRiskDecisionRecord:
        return SleeveRiskDecisionRecord.from_mapping(dict(row))

    def insert(
        self,
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
        cursor = self._conn.execute(
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
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected sleeve_risk_decisions id after insert.")
        return int(cursor.lastrowid)

    def fetch_for_account(self, *, account_id: int, limit: int) -> list[SleeveRiskDecisionRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM sleeve_risk_decisions
            WHERE account_id = ?
            ORDER BY decision_time DESC, id DESC
            LIMIT ?
            """,
            (int(account_id), int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_account_date(
        self,
        *,
        account_id: int,
        report_date: str,
    ) -> list[SleeveRiskDecisionRecord]:
        next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
        rows = self._conn.execute(
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
        return [self._row_to_record(row) for row in rows]
