from __future__ import annotations

import sqlite3

from trading.models.portfolio.daily_metric_record import DailyMetricRecord
from trading.repositories.book_bridge import book_id_for_sleeve, default_book_id

_METRIC_COLUMNS = (
    "return_pct",
    "drawdown_pct",
    "turnover_pct",
    "slippage_bps",
    "hit_rate",
    "expectancy",
    "risk_adjusted_score",
    "trade_count",
    "fees_total",
)


class DailyMetricsRepository:
    """Book-keyed daily metrics with the legacy account/sleeve access paths.

    Storage keys on ``book_id`` (UNIQUE per book+metric_date). Until P4 retires
    the sleeve paradigm, account-level rows live on the account's default book
    and sleeve rows on a bridging book named after the sleeve; both are created
    on first write.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _record(self, row: sqlite3.Row, *, sleeve_id: int | None) -> DailyMetricRecord:
        return DailyMetricRecord.from_mapping({**dict(row), "sleeve_id": sleeve_id})

    def upsert(
        self,
        *,
        account_id: int,
        sleeve_id: int | None,
        metric_date: str,
        return_pct: float | None,
        drawdown_pct: float | None,
        turnover_pct: float | None,
        slippage_bps: float | None,
        hit_rate: float | None,
        expectancy: float | None,
        risk_adjusted_score: float | None,
        trade_count: int | None,
        fees_total: float | None,
        created_at: str,
        updated_at: str,
    ) -> int:
        if sleeve_id is None:
            book_id = default_book_id(self._conn, int(account_id))
        else:
            resolved = book_id_for_sleeve(self._conn, int(sleeve_id), create=True)
            assert resolved is not None  # create=True always yields an id
            book_id = resolved

        update_set = ", ".join(f"{column} = excluded.{column}" for column in _METRIC_COLUMNS)
        cursor = self._conn.execute(
            f"""
            INSERT INTO daily_metrics (
                book_id, metric_date, {", ".join(_METRIC_COLUMNS)}, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id, metric_date) DO UPDATE SET
                {update_set},
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                metric_date,
                return_pct,
                drawdown_pct,
                turnover_pct,
                slippage_bps,
                hit_rate,
                expectancy,
                risk_adjusted_score,
                trade_count,
                fees_total,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM daily_metrics WHERE book_id = ? AND metric_date = ?",
            (int(book_id), metric_date),
        ).fetchone()
        if row is None:
            raise ValueError("Expected daily_metrics id after upsert.")
        del cursor
        return int(row[0])

    def fetch_for_account(self, *, account_id: int, limit: int) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT m.*, b.account_id AS account_id
            FROM daily_metrics m
            JOIN books b ON b.id = m.book_id
            WHERE b.account_id = ?
            ORDER BY m.metric_date DESC, m.id DESC
            LIMIT ?
            """,
            (int(account_id), int(limit)),
        ).fetchall()
        return [self._record(row, sleeve_id=None) for row in rows]

    def fetch_for_sleeve(self, *, sleeve_id: int, limit: int) -> list[DailyMetricRecord]:
        book_id = book_id_for_sleeve(self._conn, int(sleeve_id), create=False)
        if book_id is None:
            return []
        rows = self._conn.execute(
            """
            SELECT m.*, b.account_id AS account_id
            FROM daily_metrics m
            JOIN books b ON b.id = m.book_id
            WHERE m.book_id = ?
            ORDER BY m.metric_date DESC, m.id DESC
            LIMIT ?
            """,
            (int(book_id), int(limit)),
        ).fetchall()
        return [self._record(row, sleeve_id=int(sleeve_id)) for row in rows]

    def fetch_for_book(self, *, book_id: int, limit: int) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT m.*, b.account_id AS account_id
            FROM daily_metrics m
            JOIN books b ON b.id = m.book_id
            WHERE m.book_id = ?
            ORDER BY m.metric_date DESC, m.id DESC
            LIMIT ?
            """,
            (int(book_id), int(limit)),
        ).fetchall()
        return [self._record(row, sleeve_id=None) for row in rows]

    def fetch_for_book_window(
        self,
        *,
        book_id: int,
        start_date: str,
        end_date: str,
    ) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT m.*, b.account_id AS account_id
            FROM daily_metrics m
            JOIN books b ON b.id = m.book_id
            WHERE m.book_id = ?
              AND m.metric_date >= ?
              AND m.metric_date <= ?
            ORDER BY m.metric_date ASC, m.id ASC
            """,
            (int(book_id), start_date, end_date),
        ).fetchall()
        return [self._record(row, sleeve_id=None) for row in rows]

    def fetch_for_sleeve_window(
        self,
        *,
        sleeve_id: int,
        start_date: str,
        end_date: str,
    ) -> list[DailyMetricRecord]:
        book_id = book_id_for_sleeve(self._conn, int(sleeve_id), create=False)
        if book_id is None:
            return []
        rows = self._conn.execute(
            """
            SELECT m.*, b.account_id AS account_id
            FROM daily_metrics m
            JOIN books b ON b.id = m.book_id
            WHERE m.book_id = ?
              AND m.metric_date >= ?
              AND m.metric_date <= ?
            ORDER BY m.metric_date ASC, m.id ASC
            """,
            (int(book_id), start_date, end_date),
        ).fetchall()
        return [self._record(row, sleeve_id=int(sleeve_id)) for row in rows]
