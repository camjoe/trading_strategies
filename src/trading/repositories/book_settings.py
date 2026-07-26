from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

from trading.models.books.book_rotation_settings_change_event import BookRotationSettingsChangeEvent
from trading.models.books.book_rotation_settings_record import BookRotationSettingsRecord
from trading.models.books.constants import (
    BOOK_ROTATION_SETTINGS_GROUP_POLICY,
    BOOK_ROTATION_SETTINGS_GROUP_SCHEDULING,
)
from trading.repositories.unit_of_work import commit_unit_of_work

# Rotation is the one remaining 1:1 settings table (large, coherent, sparse).
# A missing row means "use code defaults". Execution and option settings are
# columns on books since revisions 0004/0005.

# Compact JSON storage keeps persisted change-event payloads stable and easy to diff.
JSON_COMPACT_SEPARATORS = (",", ":")


def _json_object_dumps(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, separators=JSON_COMPACT_SEPARATORS, sort_keys=True)


def _row_json_object(row: sqlite3.Row, key: str) -> dict[str, dict[str, object]]:
    return json.loads(str(row[key]))


def _diff_changed_fields(
    *, current: BookRotationSettingsRecord | None, new_values: Mapping[str, object]
) -> dict[str, dict[str, object]]:
    changed: dict[str, dict[str, object]] = {}
    for field_name, new_value in new_values.items():
        old_value = getattr(current, field_name) if current is not None else None
        if old_value != new_value:
            changed[field_name] = {"old": old_value, "new": new_value}
    return changed


class BookRotationSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, book_id: int) -> BookRotationSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_rotation_settings WHERE book_id = ?",
            (int(book_id),),
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
            (int(book_id), settings_group, _json_object_dumps(changed_fields), created_at),
        )

    def fetch_change_events(self, *, book_id: int, limit: int = 20) -> list[BookRotationSettingsChangeEvent]:
        rows = self._conn.execute(
            """
            SELECT * FROM book_rotation_settings_change_events
            WHERE book_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(book_id), int(limit)),
        ).fetchall()
        return [
            BookRotationSettingsChangeEvent(
                id=int(row["id"]),
                book_id=int(row["book_id"]),
                settings_group=str(row["settings_group"]),
                changed_fields=_row_json_object(row, "changed_fields"),
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
            "rotation_enabled": int(rotation_enabled),
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
                int(book_id),
                int(rotation_enabled),
                rotation_lookback_days,
                rotation_schedule,
                created_at,
                updated_at,
            ),
        )
        changed = _diff_changed_fields(current=current, new_values=new_values)
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
        cost_penalty_weight: float | None,
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
            "cost_penalty_weight": cost_penalty_weight,
            "regime_fit_weight": regime_fit_weight,
        }
        # Policy-only write: scheduling columns keep their values when the
        # row already exists; a fresh row gets scheduling defaults.
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings (
                book_id, min_trades_in_window, outperformance_threshold_bps,
                cooldown_days, risk_adjusted_return_weight, stability_weight,
                drawdown_penalty_weight, cost_penalty_weight, regime_fit_weight,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                min_trades_in_window = excluded.min_trades_in_window,
                outperformance_threshold_bps = excluded.outperformance_threshold_bps,
                cooldown_days = excluded.cooldown_days,
                risk_adjusted_return_weight = excluded.risk_adjusted_return_weight,
                stability_weight = excluded.stability_weight,
                drawdown_penalty_weight = excluded.drawdown_penalty_weight,
                cost_penalty_weight = excluded.cost_penalty_weight,
                regime_fit_weight = excluded.regime_fit_weight,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                min_trades_in_window,
                outperformance_threshold_bps,
                cooldown_days,
                risk_adjusted_return_weight,
                stability_weight,
                drawdown_penalty_weight,
                cost_penalty_weight,
                regime_fit_weight,
                created_at,
                updated_at,
            ),
        )
        changed = _diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            book_id=book_id,
            settings_group=BOOK_ROTATION_SETTINGS_GROUP_POLICY,
            changed_fields=changed,
            created_at=updated_at,
        )
        commit_unit_of_work(self._conn)
