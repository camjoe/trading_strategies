from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models.books import (
    BOOK_ROTATION_SETTINGS_GROUP_POLICY,
    BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING,
    BookRotationSettingsChangeEvent,
    BookRotationSettingsRecord,
)
from trading.persistence.change_events import diff_changed_fields
from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import commit_unit_of_work

# Rotation is the one remaining 1:1 settings table (large, coherent, sparse).
# A missing row means "use code defaults". Execution and option settings are
# columns on books since revisions 0004/0005.


class BookRotationSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, book_id: int) -> BookRotationSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_rotation_settings WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        return BookRotationSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def _insert_change_event(
        self,
        *,
        book_id: int,
        settings_group: str,
        changed_fields: dict[str, dict[str, object]],
        created_at: str,
    ) -> None:
        if not changed_fields:
            return
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings_change_events (
                book_id, settings_group, changed_fields, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (book_id, settings_group, dumps_json_column(changed_fields), created_at),
        )

    def fetch_change_events(self, *, book_id: int, limit: int = 20) -> list[BookRotationSettingsChangeEvent]:
        rows = self._conn.execute(
            """
            SELECT * FROM book_rotation_settings_change_events
            WHERE book_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (book_id, limit),
        ).fetchall()
        return [BookRotationSettingsChangeEvent.from_mapping(dict(row)) for row in rows]

    def _upsert_group(
        self,
        *,
        book_id: int,
        values: Mapping[str, object],
        settings_group: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Write one settings group and record what changed.

        `ON CONFLICT` assigns only the named columns, so the other group keeps
        its stored values; a fresh row takes DDL defaults for the columns this
        write omits. Column names come from the calling method, never a caller.
        """
        current = self.fetch(book_id=book_id)
        columns = tuple(values)
        placeholders = ", ".join("?" for _ in range(len(columns) + 3))
        assignments = ", ".join(f"{column} = excluded.{column}" for column in columns)
        self._conn.execute(
            f"""
            INSERT INTO book_rotation_settings (
                book_id, {", ".join(columns)}, created_at, updated_at
            )
            VALUES ({placeholders})
            ON CONFLICT(book_id) DO UPDATE SET
                {assignments},
                updated_at = excluded.updated_at
            """,
            (book_id, *values.values(), created_at, updated_at),
        )
        self._insert_change_event(
            book_id=book_id,
            settings_group=settings_group,
            changed_fields=diff_changed_fields(current=current, new_values=dict(values)),
            created_at=updated_at,
        )
        commit_unit_of_work(self._conn)

    def upsert_rotation_scheduling(
        self,
        *,
        book_id: int,
        rotation_enabled: int = 0,
        rotation_lookback_days: int | None = None,
        rotation_schedule: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._upsert_group(
            book_id=book_id,
            values={
                "rotation_enabled": rotation_enabled,
                "rotation_lookback_days": rotation_lookback_days,
                "rotation_schedule": rotation_schedule,
            },
            settings_group=BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING,
            created_at=created_at,
            updated_at=updated_at,
        )

    def upsert_rotation_policy(
        self,
        *,
        book_id: int,
        min_trades_in_window: int | None,
        outperformance_threshold_bps: float | None,
        cooldown_days: int | None,
        risk_adjusted_return_weight: float | None,
        stability_weight: float | None,
        drawdown_penalty_weight: float | None,
        regime_fit_weight: float | None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._upsert_group(
            book_id=book_id,
            values={
                "min_trades_in_window": min_trades_in_window,
                "outperformance_threshold_bps": outperformance_threshold_bps,
                "cooldown_days": cooldown_days,
                "risk_adjusted_return_weight": risk_adjusted_return_weight,
                "stability_weight": stability_weight,
                "drawdown_penalty_weight": drawdown_penalty_weight,
                "regime_fit_weight": regime_fit_weight,
            },
            settings_group=BOOK_ROTATION_SETTINGS_GROUP_POLICY,
            created_at=created_at,
            updated_at=updated_at,
        )
