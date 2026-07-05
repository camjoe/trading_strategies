from __future__ import annotations

import sqlite3

from trading.models.portfolio.daily_metric_record import DailyMetricRecord

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

    def _default_book_id(self, account_id: int) -> int:
        row = self._conn.execute(
            "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
            (int(account_id),),
        ).fetchone()
        if row is not None:
            return int(row[0])
        cursor = self._conn.execute(
            """
            INSERT INTO books (
                account_id, name, status, is_default, start_equity, current_cash,
                current_equity, trade_universes, goal_min_return_pct,
                goal_max_return_pct, goal_period, created_at, updated_at
            )
            SELECT id, 'default', 'active', 1, initial_cash, initial_cash, initial_cash,
                   trade_universes, goal_min_return_pct, goal_max_return_pct, goal_period,
                   created_at, created_at
            FROM accounts WHERE id = ?
            """,
            (int(account_id),),
        )
        if cursor.rowcount == 0:
            raise LookupError(f"Account {account_id} does not exist; cannot resolve its default book.")
        return int(cursor.lastrowid or 0)

    def _book_id_for_sleeve(self, sleeve_id: int, *, create: bool) -> int | None:
        """Bridge a legacy sleeve to its book (same account, book named after the sleeve)."""
        sleeve = self._conn.execute(
            "SELECT account_id, name, start_equity, current_cash, current_equity, created_at "
            "FROM strategy_sleeves WHERE id = ?",
            (int(sleeve_id),),
        ).fetchone()
        if sleeve is None:
            raise LookupError(f"Sleeve {sleeve_id} does not exist; cannot resolve its book.")
        row = self._conn.execute(
            "SELECT id FROM books WHERE account_id = ? AND name = ?",
            (int(sleeve["account_id"]), str(sleeve["name"])),
        ).fetchone()
        if row is not None:
            return int(row[0])
        if not create:
            return None
        cursor = self._conn.execute(
            """
            INSERT INTO books (
                account_id, name, status, is_default, start_equity, current_cash,
                current_equity, created_at, updated_at
            )
            VALUES (?, ?, 'active', 0, ?, ?, ?, ?, ?)
            """,
            (
                int(sleeve["account_id"]),
                str(sleeve["name"]),
                float(sleeve["start_equity"]),
                float(sleeve["current_cash"]),
                float(sleeve["current_equity"]),
                str(sleeve["created_at"]),
                str(sleeve["created_at"]),
            ),
        )
        return int(cursor.lastrowid or 0)

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
            book_id = self._default_book_id(int(account_id))
        else:
            resolved = self._book_id_for_sleeve(int(sleeve_id), create=True)
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
        book_id = self._book_id_for_sleeve(int(sleeve_id), create=False)
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

    def fetch_for_sleeve_window(
        self,
        *,
        sleeve_id: int,
        start_date: str,
        end_date: str,
    ) -> list[DailyMetricRecord]:
        book_id = self._book_id_for_sleeve(int(sleeve_id), create=False)
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
