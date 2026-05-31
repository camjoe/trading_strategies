from __future__ import annotations

import sqlite3

from trading.models.daily_metric_record import DailyMetricRecord


class DailyMetricsRepository:

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> DailyMetricRecord:
        return DailyMetricRecord.from_mapping(dict(row))

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
        existing = self._conn.execute(
            """
            SELECT id
            FROM daily_metrics
            WHERE account_id = ?
              AND metric_date = ?
              AND (
                    (sleeve_id = ?)
                    OR (sleeve_id IS NULL AND ? IS NULL)
                  )
            LIMIT 1
            """,
            (
                int(account_id),
                metric_date,
                None if sleeve_id is None else int(sleeve_id),
                None if sleeve_id is None else int(sleeve_id),
            ),
        ).fetchone()

        if existing is not None:
            metric_id = int(existing["id"])
            self._conn.execute(
                """
                UPDATE daily_metrics
                SET return_pct = ?,
                    drawdown_pct = ?,
                    turnover_pct = ?,
                    slippage_bps = ?,
                    hit_rate = ?,
                    expectancy = ?,
                    risk_adjusted_score = ?,
                    trade_count = ?,
                    fees_total = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    return_pct,
                    drawdown_pct,
                    turnover_pct,
                    slippage_bps,
                    hit_rate,
                    expectancy,
                    risk_adjusted_score,
                    trade_count,
                    fees_total,
                    updated_at,
                    metric_id,
                ),
            )
            self._conn.commit()
            return metric_id

        cursor = self._conn.execute(
            """
            INSERT INTO daily_metrics (
                account_id,
                sleeve_id,
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
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                None if sleeve_id is None else int(sleeve_id),
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
        if cursor.lastrowid is None:
            raise ValueError("Expected daily_metrics id after insert.")
        return int(cursor.lastrowid)

    def fetch_for_account(self, *, account_id: int, limit: int) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM daily_metrics
            WHERE account_id = ?
            ORDER BY metric_date DESC, id DESC
            LIMIT ?
            """,
            (int(account_id), int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_sleeve(self, *, sleeve_id: int, limit: int) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM daily_metrics
            WHERE sleeve_id = ?
            ORDER BY metric_date DESC, id DESC
            LIMIT ?
            """,
            (int(sleeve_id), int(limit)),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_sleeve_window(
        self,
        *,
        sleeve_id: int,
        start_date: str,
        end_date: str,
    ) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM daily_metrics
            WHERE sleeve_id = ?
              AND metric_date >= ?
              AND metric_date <= ?
            ORDER BY metric_date ASC, id ASC
            """,
            (int(sleeve_id), start_date, end_date),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
