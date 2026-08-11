from __future__ import annotations

import sqlite3

from trading.models.portfolio import DailyMetricRecord
from trading.persistence.unit_of_work import commit_unit_of_work

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

# Every record read joins the owning book to carry account_id alongside the
# stored row; only the filter and ordering differ.
_BOOK_ROWS_SELECT = """
SELECT m.*, b.account_id AS account_id
FROM daily_metrics m
JOIN books b ON b.id = m.book_id
"""


class DailyMetricsRepository:
    """Book-keyed daily metrics.

    Grain: **book-native, non-additive**. Daily percentages (return, drawdown,
    turnover, hit rate) do not sum across books, so there is no account roll-up:
    ``fetch_book_rows_for_account`` returns one row *per book* per date, not an
    aggregated account row. Contrast ``EquitySnapshotRepository`` (book-additive
    SUM roll-up) and ``RiskSnapshotRepository`` (account-emergent); see
    docs/reference/performance-and-risk-tables.md.

    Storage keys on ``book_id`` (UNIQUE per book+metric_date).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(
        self,
        *,
        book_id: int,
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
        update_set = ", ".join(f"{column} = excluded.{column}" for column in _METRIC_COLUMNS)
        self._conn.execute(
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
                book_id,
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
        commit_unit_of_work(self._conn)
        row = self._conn.execute(
            "SELECT id FROM daily_metrics WHERE book_id = ? AND metric_date = ?",
            (book_id, metric_date),
        ).fetchone()
        if row is None:
            raise ValueError("Expected daily_metrics id after upsert.")
        return int(row[0])

    def fetch_book_rows_for_account(self, *, account_id: int, limit: int) -> list[DailyMetricRecord]:
        """Return per-book daily-metric rows for the account (NOT an aggregate).

        Daily percentages don't sum across books, so this is a flat list of each
        book's rows (most recent first), not a rolled-up account row. Callers
        that want an account total must aggregate additive fields themselves.
        """
        rows = self._conn.execute(
            _BOOK_ROWS_SELECT + "WHERE b.account_id = ? ORDER BY m.metric_date DESC, m.id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return [DailyMetricRecord.from_mapping(dict(row)) for row in rows]

    def fetch_for_book(self, *, book_id: int, limit: int) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            _BOOK_ROWS_SELECT + "WHERE m.book_id = ? ORDER BY m.metric_date DESC, m.id DESC LIMIT ?",
            (book_id, limit),
        ).fetchall()
        return [DailyMetricRecord.from_mapping(dict(row)) for row in rows]

    def fetch_recent_returns_for_book(self, *, book_id: int, before_date: str, limit: int) -> list[float]:
        """Most-recent-first non-null daily returns strictly before ``before_date``.

        Feeds the trailing risk-adjusted score: the prior sessions whose
        ``return_pct`` values combine with the current day to form its window.
        Days with no return (``return_pct IS NULL`` — e.g. a book's first day)
        are excluded so the score is computed over actual return observations.
        """
        rows = self._conn.execute(
            """
            SELECT return_pct
            FROM daily_metrics
            WHERE book_id = ?
              AND metric_date < ?
              AND return_pct IS NOT NULL
            ORDER BY metric_date DESC, id DESC
            LIMIT ?
            """,
            (book_id, before_date, limit),
        ).fetchall()
        return [float(row[0]) for row in rows]

    def fetch_for_book_window(
        self,
        *,
        book_id: int,
        start_date: str,
        end_date: str,
    ) -> list[DailyMetricRecord]:
        rows = self._conn.execute(
            _BOOK_ROWS_SELECT + "WHERE m.book_id = ? AND m.metric_date >= ? AND m.metric_date <= ? "
            "ORDER BY m.metric_date ASC, m.id ASC",
            (book_id, start_date, end_date),
        ).fetchall()
        return [DailyMetricRecord.from_mapping(dict(row)) for row in rows]
