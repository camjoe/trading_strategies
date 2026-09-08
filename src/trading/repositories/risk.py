from __future__ import annotations

import sqlite3
from dataclasses import fields

from common.time import next_date_str
from trading.models.books import (
    RiskDecisionInsert,
    RiskDecisionRecord,
    RiskSnapshotInsert,
    RiskSnapshotRecord,
)
from trading.persistence.unit_of_work import commit_unit_of_work


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"


# Derived rather than listed: the payload's field names are the column names, so a
# new column is added in one place. Each *Record subclasses its *Insert, so the
# projection also drops `id` when a record is passed back in.
_SNAPSHOT_COLUMNS = tuple(field.name for field in fields(RiskSnapshotInsert))
_SNAPSHOT_INSERT_SQL = _insert_sql("risk_snapshots", _SNAPSHOT_COLUMNS)
_DECISION_COLUMNS = tuple(field.name for field in fields(RiskDecisionInsert))
_DECISION_INSERT_SQL = _insert_sql("risk_decisions", _DECISION_COLUMNS)


class RiskSnapshotRepository:
    """SQL access for clean-schema risk_snapshots (successor to portfolio_risk_snapshots).

    Grain: **account-emergent**, by design. Gross/net exposure are additive, but
    concentration is a portfolio property that cannot be reconstructed from
    per-book maxima (a symbol under-concentrated in each book can be
    over-concentrated in aggregate), and the risk gate enforces its caps at the
    account level. So there is no per-book risk row and no roll-up. Contrast
    ``EquitySnapshotRepository`` (book-additive) and ``DailyMetricsRepository``
    (book-native); see docs/reference/performance-and-risk-tables.md.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, snapshot: RiskSnapshotInsert) -> int:
        cursor = self._conn.execute(
            _SNAPSHOT_INSERT_SQL,
            tuple(getattr(snapshot, column) for column in _SNAPSHOT_COLUMNS),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def fetch_latest(self, *, account_id: int) -> RiskSnapshotRecord | None:
        row = self._conn.execute(
            "SELECT * FROM risk_snapshots WHERE account_id = ? ORDER BY snapshot_time DESC LIMIT 1",
            (account_id,),
        ).fetchone()
        return RiskSnapshotRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_latest_as_of(self, *, account_id: int, report_date: str) -> RiskSnapshotRecord | None:
        """Latest snapshot on or before ``report_date`` — kill-switch state as of that day.

        Date-scoped counterpart to ``fetch_latest`` for historical/backfilled
        reports, so a report for a past date reflects that day's state rather
        than the current one.
        """
        next_date = next_date_str(report_date)
        row = self._conn.execute(
            "SELECT * FROM risk_snapshots WHERE account_id = ? AND snapshot_time < ? "
            "ORDER BY snapshot_time DESC LIMIT 1",
            (account_id, next_date),
        ).fetchone()
        return RiskSnapshotRecord.from_mapping(dict(row)) if row is not None else None


class RiskDecisionRepository:
    """SQL access for the clean-schema risk_decisions table."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, decision: RiskDecisionInsert) -> int:
        cursor = self._conn.execute(
            _DECISION_INSERT_SQL,
            tuple(getattr(decision, column) for column in _DECISION_COLUMNS),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def fetch_recent(self, *, account_id: int, limit: int = 50) -> list[RiskDecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM risk_decisions WHERE account_id = ? ORDER BY decision_time DESC, id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return [RiskDecisionRecord.from_mapping(dict(row)) for row in rows]

    def fetch_for_account_date(self, *, account_id: int, report_date: str) -> list[RiskDecisionRecord]:
        next_date = next_date_str(report_date)
        rows = self._conn.execute(
            """
            SELECT * FROM risk_decisions
            WHERE account_id = ? AND decision_time >= ? AND decision_time < ?
            ORDER BY decision_time ASC, id ASC
            """,
            (account_id, report_date, next_date),
        ).fetchall()
        return [RiskDecisionRecord.from_mapping(dict(row)) for row in rows]
