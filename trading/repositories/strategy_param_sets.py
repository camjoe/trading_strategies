from __future__ import annotations

import sqlite3

from trading.models.strategy_param_set_record import StrategyParamSetRecord


class StrategyParamSetRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> StrategyParamSetRecord:
        return StrategyParamSetRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        strategy_name: str,
        version: str,
        params_json: str,
        config_version: str | None,
        is_active: int,
        created_at: str,
        updated_at: str,
        activated_at: str | None,
        deactivated_at: str | None,
        notes: str | None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO strategy_param_sets (
                strategy_name,
                version,
                params_json,
                config_version,
                is_active,
                created_at,
                updated_at,
                activated_at,
                deactivated_at,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_name,
                version,
                params_json,
                config_version,
                int(is_active),
                created_at,
                updated_at,
                activated_at,
                deactivated_at,
                notes,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected strategy_param_sets id after insert.")
        return int(cursor.lastrowid)

    def fetch_by_id(self, *, param_set_id: int) -> StrategyParamSetRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategy_param_sets WHERE id = ?",
            (int(param_set_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_active(self, *, strategy_name: str) -> StrategyParamSetRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM strategy_param_sets
            WHERE strategy_name = ? AND is_active = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (strategy_name,),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def set_activation(
        self,
        *,
        param_set_id: int,
        is_active: int,
        updated_at: str,
        activated_at: str | None,
        deactivated_at: str | None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE strategy_param_sets
            SET is_active = ?, updated_at = ?, activated_at = ?, deactivated_at = ?
            WHERE id = ?
            """,
            (
                int(is_active),
                updated_at,
                activated_at,
                deactivated_at,
                int(param_set_id),
            ),
        )
        self._conn.commit()
