from __future__ import annotations

import sqlite3

from trading.models.units.trading_unit_record import TradingUnitRecord


class TradingUnitRepository:
    """SQL access for trading_units — the clean-schema execution primitive.

    The one-default-unit-per-account invariant is enforced by the partial unique
    index `idx_trading_units_default_per_account`; violations surface as
    sqlite3.IntegrityError.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> TradingUnitRecord:
        return TradingUnitRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        account_id: int,
        name: str,
        status: str = "active",
        is_default: int = 0,
        start_equity: float,
        current_cash: float,
        current_equity: float,
        trade_universes: str | None = None,
        goal_min_return_pct: float | None = None,
        goal_max_return_pct: float | None = None,
        goal_period: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO trading_units (
                account_id, name, status, is_default, start_equity, current_cash,
                current_equity, trade_universes, goal_min_return_pct,
                goal_max_return_pct, goal_period, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                name,
                status,
                int(is_default),
                float(start_equity),
                float(current_cash),
                float(current_equity),
                trade_universes,
                goal_min_return_pct,
                goal_max_return_pct,
                goal_period,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def fetch_by_id(self, *, unit_id: int) -> TradingUnitRecord | None:
        row = self._conn.execute(
            "SELECT * FROM trading_units WHERE id = ?",
            (int(unit_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_for_account(self, *, account_id: int) -> list[TradingUnitRecord]:
        rows = self._conn.execute(
            "SELECT * FROM trading_units WHERE account_id = ? ORDER BY id ASC",
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_default_for_account(self, *, account_id: int) -> TradingUnitRecord | None:
        row = self._conn.execute(
            "SELECT * FROM trading_units WHERE account_id = ? AND is_default = 1",
            (int(account_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def update_status(self, *, unit_id: int, status: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE trading_units SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, int(unit_id)),
        )
        self._conn.commit()

    def update_balances(
        self,
        *,
        unit_id: int,
        current_cash: float,
        current_equity: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            UPDATE trading_units
            SET current_cash = ?, current_equity = ?, updated_at = ?
            WHERE id = ?
            """,
            (float(current_cash), float(current_equity), updated_at, int(unit_id)),
        )
        self._conn.commit()
