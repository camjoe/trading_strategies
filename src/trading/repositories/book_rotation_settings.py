from __future__ import annotations

import sqlite3

from trading.models.books import (
    BOOK_ROTATION_SETTINGS_GROUP_POLICY,
    BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING,
    BookRotationSettingsChangeEvent,
    BookRotationSettingsRecord,
)
from trading.persistence.change_events import diff_changed_fields
from trading.persistence.json_columns import dumps_json_column, read_json_object
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
        return [
            BookRotationSettingsChangeEvent(
                id=int(row["id"]),
                book_id=int(row["book_id"]),
                settings_group=str(row["settings_group"]),
                changed_fields=read_json_object(row, "changed_fields"),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

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
        current = self.fetch(book_id=book_id)
        new_values = {
            "rotation_enabled": rotation_enabled,
            "rotation_lookback_days": rotation_lookback_days,
            "rotation_schedule": rotation_schedule,
        }
        # Scheduling-only write: policy columns keep their values when the
        # row already exists; a fresh row gets policy NULLs (code defaults).
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings (
                book_id, rotation_enabled, rotation_lookback_days, rotation_schedule,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                rotation_enabled = excluded.rotation_enabled,
                rotation_lookback_days = excluded.rotation_lookback_days,
                rotation_schedule = excluded.rotation_schedule,
                updated_at = excluded.updated_at
            """,
            (
                book_id,
                rotation_enabled,
                rotation_lookback_days,
                rotation_schedule,
                created_at,
                updated_at,
            ),
        )
        changed = diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            book_id=book_id,
            settings_group=BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING,
            changed_fields=changed,
            created_at=updated_at,
        )
        commit_unit_of_work(self._conn)

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
        current = self.fetch(book_id=book_id)
        new_values = {
            "min_trades_in_window": min_trades_in_window,
            "outperformance_threshold_bps": outperformance_threshold_bps,
            "cooldown_days": cooldown_days,
            "risk_adjusted_return_weight": risk_adjusted_return_weight,
            "stability_weight": stability_weight,
            "drawdown_penalty_weight": drawdown_penalty_weight,
            "regime_fit_weight": regime_fit_weight,
        }
        # Policy-only write: scheduling columns keep their values when the
        # row already exists; a fresh row gets scheduling defaults.
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings (
                book_id, min_trades_in_window, outperformance_threshold_bps,
                cooldown_days, risk_adjusted_return_weight, stability_weight,
                drawdown_penalty_weight, regime_fit_weight,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                min_trades_in_window = excluded.min_trades_in_window,
                outperformance_threshold_bps = excluded.outperformance_threshold_bps,
                cooldown_days = excluded.cooldown_days,
                risk_adjusted_return_weight = excluded.risk_adjusted_return_weight,
                stability_weight = excluded.stability_weight,
                drawdown_penalty_weight = excluded.drawdown_penalty_weight,
                regime_fit_weight = excluded.regime_fit_weight,
                updated_at = excluded.updated_at
            """,
            (
                book_id,
                min_trades_in_window,
                outperformance_threshold_bps,
                cooldown_days,
                risk_adjusted_return_weight,
                stability_weight,
                drawdown_penalty_weight,
                regime_fit_weight,
                created_at,
                updated_at,
            ),
        )
        changed = diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            book_id=book_id,
            settings_group=BOOK_ROTATION_SETTINGS_GROUP_POLICY,
            changed_fields=changed,
            created_at=updated_at,
        )
        commit_unit_of_work(self._conn)
