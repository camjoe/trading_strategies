from __future__ import annotations

import sqlite3

from trading.models.sleeves.sleeve_position_record import SleevePositionRecord


class SleevePositionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> SleevePositionRecord:
        return SleevePositionRecord.from_mapping(dict(row))

    def upsert(
        self,
        *,
        sleeve_id: int,
        symbol: str,
        qty: float,
        avg_cost: float,
        market_value: float,
        unrealized_pnl: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO sleeve_positions (
                sleeve_id,
                symbol,
                qty,
                avg_cost,
                market_value,
                unrealized_pnl,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sleeve_id, symbol)
            DO UPDATE SET
                qty = excluded.qty,
                avg_cost = excluded.avg_cost,
                market_value = excluded.market_value,
                unrealized_pnl = excluded.unrealized_pnl,
                updated_at = excluded.updated_at
            """,
            (
                int(sleeve_id),
                symbol,
                float(qty),
                float(avg_cost),
                float(market_value),
                float(unrealized_pnl),
                updated_at,
            ),
        )
        self._conn.commit()

    def delete(self, *, sleeve_id: int, symbol: str) -> None:
        self._conn.execute(
            "DELETE FROM sleeve_positions WHERE sleeve_id = ? AND symbol = ?",
            (int(sleeve_id), symbol),
        )
        self._conn.commit()

    def fetch(self, *, sleeve_id: int, symbol: str) -> SleevePositionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sleeve_positions WHERE sleeve_id = ? AND symbol = ?",
            (int(sleeve_id), symbol),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_for_sleeve(self, *, sleeve_id: int) -> list[SleevePositionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM sleeve_positions WHERE sleeve_id = ? ORDER BY symbol ASC",
            (int(sleeve_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_account(self, *, account_id: int) -> list[SleevePositionRecord]:
        rows = self._conn.execute(
            """
            SELECT p.*
            FROM sleeve_positions p
            JOIN strategy_sleeves s ON s.id = p.sleeve_id
            WHERE s.account_id = ?
            ORDER BY p.sleeve_id ASC, p.symbol ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
