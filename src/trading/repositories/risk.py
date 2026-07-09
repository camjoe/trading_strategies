from __future__ import annotations

import datetime as dt
import sqlite3

from trading.models.books.risk_decision_record import RiskDecisionRecord
from trading.models.books.risk_snapshot_record import RiskSnapshotRecord


class RiskSnapshotRepository:
    """SQL access for clean-schema risk_snapshots (successor to portfolio_risk_snapshots)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        account_id: int,
        snapshot_time: str,
        gross_exposure: float,
        net_exposure: float,
        max_symbol_concentration_pct: float,
        max_sector_concentration_pct: float,
        drawdown_pct: float | None = None,
        leverage_proxy: float | None = None,
        daily_loss_pct: float | None = None,
        kill_switch_triggered: int = 0,
        risk_payload_json: str = "{}",
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO risk_snapshots (
                account_id, snapshot_time, gross_exposure, net_exposure,
                max_symbol_concentration_pct, max_sector_concentration_pct,
                drawdown_pct, leverage_proxy, daily_loss_pct,
                kill_switch_triggered, risk_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                snapshot_time,
                float(gross_exposure),
                float(net_exposure),
                float(max_symbol_concentration_pct),
                float(max_sector_concentration_pct),
                drawdown_pct,
                leverage_proxy,
                daily_loss_pct,
                int(kill_switch_triggered),
                risk_payload_json,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def fetch_latest(self, *, account_id: int) -> RiskSnapshotRecord | None:
        row = self._conn.execute(
            "SELECT * FROM risk_snapshots WHERE account_id = ? ORDER BY snapshot_time DESC LIMIT 1",
            (int(account_id),),
        ).fetchone()
        return RiskSnapshotRecord.from_mapping(dict(row)) if row is not None else None


class RiskDecisionRepository:
    """SQL access for clean-schema risk_decisions (successor to sleeve_risk_decisions)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        account_id: int,
        book_id: int | None = None,
        decision_time: str,
        symbol: str | None = None,
        side: str | None = None,
        action: str,
        reason_code: str,
        requested_qty: int | None = None,
        approved_qty: int | None = None,
        requested_notional: float | None = None,
        approved_notional: float | None = None,
        risk_payload_json: str = "{}",
        created_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO risk_decisions (
                account_id, book_id, decision_time, symbol, side, action, reason_code,
                requested_qty, approved_qty, requested_notional, approved_notional,
                risk_payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                book_id,
                decision_time,
                symbol,
                side,
                action,
                reason_code,
                requested_qty,
                approved_qty,
                requested_notional,
                approved_notional,
                risk_payload_json,
                created_at,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def fetch_recent(self, *, account_id: int, limit: int = 50) -> list[RiskDecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM risk_decisions WHERE account_id = ? ORDER BY decision_time DESC, id DESC LIMIT ?",
            (int(account_id), int(limit)),
        ).fetchall()
        return [RiskDecisionRecord.from_mapping(dict(row)) for row in rows]

    def fetch_for_account_date(self, *, account_id: int, report_date: str) -> list[RiskDecisionRecord]:
        next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
        rows = self._conn.execute(
            """
            SELECT * FROM risk_decisions
            WHERE account_id = ? AND decision_time >= ? AND decision_time < ?
            ORDER BY decision_time ASC, id ASC
            """,
            (int(account_id), report_date, next_date),
        ).fetchall()
        return [RiskDecisionRecord.from_mapping(dict(row)) for row in rows]
