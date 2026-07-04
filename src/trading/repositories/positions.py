from __future__ import annotations

import sqlite3

from trading.models.units.position_record import PositionRecord


class PositionRepository:
    """SQL access for the clean-schema positions table, keyed (unit_id, symbol)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> PositionRecord:
        return PositionRecord.from_mapping(dict(row))

    def upsert(
        self,
        *,
        unit_id: int,
        symbol: str,
        qty: float,
        avg_cost: float,
        market_value: float,
        unrealized_pnl: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO positions (
                unit_id, symbol, qty, avg_cost, market_value, unrealized_pnl, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id, symbol) DO UPDATE SET
                qty = excluded.qty,
                avg_cost = excluded.avg_cost,
                market_value = excluded.market_value,
                unrealized_pnl = excluded.unrealized_pnl,
                updated_at = excluded.updated_at
            """,
            (
                int(unit_id),
                symbol,
                float(qty),
                float(avg_cost),
                float(market_value),
                float(unrealized_pnl),
                updated_at,
            ),
        )
        self._conn.commit()

    def delete(self, *, unit_id: int, symbol: str) -> None:
        self._conn.execute(
            "DELETE FROM positions WHERE unit_id = ? AND symbol = ?",
            (int(unit_id), symbol),
        )
        self._conn.commit()

    def fetch(self, *, unit_id: int, symbol: str) -> PositionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE unit_id = ? AND symbol = ?",
            (int(unit_id), symbol),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_for_unit(self, *, unit_id: int) -> list[PositionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE unit_id = ? ORDER BY symbol ASC",
            (int(unit_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_account(self, *, account_id: int) -> list[PositionRecord]:
        rows = self._conn.execute(
            """
            SELECT p.*
            FROM positions p
            JOIN trading_units u ON u.id = p.unit_id
            WHERE u.account_id = ?
            ORDER BY p.unit_id ASC, p.symbol ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
