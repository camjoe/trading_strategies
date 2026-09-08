from __future__ import annotations

import sqlite3

from trading.models.strategy import StrategyRecord
from trading.persistence.unit_of_work import commit_unit_of_work


class StrategyImmutableError(ValueError):
    """Raised when attempting to modify the knobs of a non-draft strategy row."""


def _draft_primitive(key: str) -> str:
    """Canonical primitive id for a drafted label.

    A draft records the canonical code primitive its label resolves to (e.g.
    ``momentum`` -> ``trend``) so the catalog stays internally consistent. An
    unrecognized label keeps the raw key as a placeholder primitive, which the
    catalog resolver reports as unresolvable at read time. Style and required
    features are code-owned (``PrimitiveSpec``) and no longer stored.
    """
    from trading.domain.strategies.resolution import resolve_strategy

    try:
        return resolve_strategy(key).strategy_id
    except ValueError:
        return key


class StrategyRepository:
    """SQL access for the strategies catalog (a strategy = primitive + knobs).

    Immutability guard: a strategy's primitive/knobs are editable only while
    `status = 'draft'`. Freezing is one-way; tuning a frozen strategy means
    inserting a new row.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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
                enabled,
                created_at,
                updated_at,
            ),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def ensure_id_for_label(self, *, label: str | None, now_iso: str, create: bool = True) -> int | None:
        """Resolve a strategy label to a catalog row id, drafting the row when unknown.

        Leaves the commit to the caller's ``unit_of_work`` scope, unlike every
        other write here.
        """
        if label is None or not label.strip():
            return None
        key = label.strip().lower()
        row = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (key,)).fetchone()
        if row is not None:
            return int(row[0])
        if not create:
            return None
        cursor = self._conn.execute(
            """
            INSERT INTO strategies (
                strategy_key, primitive, params_json, status, enabled, created_at, updated_at
            )
            VALUES (?, ?, '{}', 'draft', 1, ?, ?)
            """,
            (key, _draft_primitive(key), now_iso, now_iso),
        )
        return int(cursor.lastrowid or 0)

    def fetch_by_id(self, *, strategy_id: int) -> StrategyRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE id = ?",
            (strategy_id,),
        ).fetchone()
        return StrategyRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_by_key(self, *, strategy_key: str) -> StrategyRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE strategy_key = ?",
            (strategy_key,),
        ).fetchone()
        return StrategyRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_all(self) -> list[StrategyRecord]:
        rows = self._conn.execute("SELECT * FROM strategies ORDER BY strategy_key ASC").fetchall()
        return [StrategyRecord.from_mapping(dict(row)) for row in rows]

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
            (primitive, params_json, updated_at, strategy_id),
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
            (updated_at, strategy_id),
        )
        commit_unit_of_work(self._conn)

    def set_enabled(self, *, strategy_id: int, enabled: int, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE strategies SET enabled = ?, updated_at = ? WHERE id = ?",
            (enabled, updated_at, strategy_id),
        )
        commit_unit_of_work(self._conn)
