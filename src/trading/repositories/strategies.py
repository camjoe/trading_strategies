from __future__ import annotations

import sqlite3

from trading.models.strategy import StrategyRecord
from trading.repositories.unit_of_work import commit_unit_of_work


class StrategyImmutableError(ValueError):
    """Raised when attempting to modify the knobs of a non-draft strategy row."""


class StrategyRepository:
    """SQL access for the strategies catalog (a strategy = primitive + knobs).

    Immutability guard: a strategy's primitive/knobs are editable only while
    `status = 'draft'`. Freezing is one-way; tuning a frozen strategy means
    inserting a new row.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> StrategyRecord:
        return StrategyRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        strategy_key: str,
        primitive: str,
        params_json: str,
        description: str | None = None,
        status: str = "draft",
        enabled: int = 1,
        created_at: str,
        updated_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO strategies (
                strategy_key, primitive, params_json,
                description, status, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_key,
                primitive,
                params_json,
                description,
                status,
                int(enabled),
                created_at,
                updated_at,
            ),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def fetch_by_id(self, *, strategy_id: int) -> StrategyRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE id = ?",
            (int(strategy_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_by_key(self, *, strategy_key: str) -> StrategyRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE strategy_key = ?",
            (strategy_key,),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_all(self) -> list[StrategyRecord]:
        rows = self._conn.execute("SELECT * FROM strategies ORDER BY strategy_key ASC").fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_enabled(self) -> list[StrategyRecord]:
        rows = self._conn.execute(
            "SELECT * FROM strategies WHERE enabled = 1 AND status != 'retired' ORDER BY strategy_key ASC"
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_draft_knobs(
        self,
        *,
        strategy_id: int,
        primitive: str,
        params_json: str,
        updated_at: str,
    ) -> None:
        """Update a draft strategy's primitive/knobs; rejects non-draft rows (invariant 5)."""
        cursor = self._conn.execute(
            """
            UPDATE strategies
            SET primitive = ?, params_json = ?, updated_at = ?
            WHERE id = ? AND status = 'draft'
            """,
            (primitive, params_json, updated_at, int(strategy_id)),
        )
        if cursor.rowcount == 0:
            raise StrategyImmutableError(
                f"Strategy {strategy_id} is frozen or missing; tuning requires a new strategy row."
            )
        commit_unit_of_work(self._conn)

    def freeze(self, *, strategy_id: int, updated_at: str) -> None:
        """Mark a strategy frozen (one-way; called once it has evidence or goes live)."""
        self._conn.execute(
            "UPDATE strategies SET status = 'frozen', updated_at = ? WHERE id = ? AND status = 'draft'",
            (updated_at, int(strategy_id)),
        )
        commit_unit_of_work(self._conn)

    def set_enabled(self, *, strategy_id: int, enabled: int, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE strategies SET enabled = ?, updated_at = ? WHERE id = ?",
            (int(enabled), updated_at, int(strategy_id)),
        )
        commit_unit_of_work(self._conn)
