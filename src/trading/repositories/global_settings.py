from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models.settings import (
    GLOBAL_SETTINGS_GROUP_EVALUATION,
    GLOBAL_SETTINGS_GROUP_PROMOTION,
    GLOBAL_SETTINGS_GROUP_THROTTLE,
    GlobalSettingsChangeEvent,
    GlobalSettingsRecord,
)
from trading.persistence.change_events import diff_changed_fields
from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import commit_unit_of_work

# global_settings holds one row. Every write targets it and the schema enforces
# that with a CHECK on the primary key.
_SINGLETON_ID = 1


class GlobalSettingsRepository:
    """Persist optional operator overrides for global operational policy."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self) -> GlobalSettingsRecord | None:
        row = self._conn.execute("SELECT * FROM global_settings WHERE id = ?", (_SINGLETON_ID,)).fetchone()
        return GlobalSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def _insert_change_event(
        self, *, settings_group: str, changed_fields: dict[str, dict[str, object]], created_at: str
    ) -> None:
        if not changed_fields:
            return
        self._conn.execute(
            """
            INSERT INTO global_settings_change_events (
                settings_group, changed_fields, created_at
            ) VALUES (?, ?, ?)
            """,
            (settings_group, dumps_json_column(changed_fields), created_at),
        )

    def fetch_change_events(self, *, limit: int = 20) -> list[GlobalSettingsChangeEvent]:
        rows = self._conn.execute(
            """
            SELECT * FROM global_settings_change_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [GlobalSettingsChangeEvent.from_mapping(dict(row)) for row in rows]

    def _upsert_group(self, *, values: Mapping[str, object], settings_group: str, updated_at: str) -> None:
        """Write one settings group to the singleton row and record what changed.

        `ON CONFLICT` assigns only the named columns, so the other groups keep
        their stored values; a first write leaves them at their DDL defaults.
        Column names come from the calling method, never a caller.
        """
        current = self.fetch()
        columns = tuple(values)
        placeholders = ", ".join("?" for _ in range(len(columns) + 2))
        assignments = ", ".join(f"{column} = excluded.{column}" for column in columns)
        self._conn.execute(
            f"""
            INSERT INTO global_settings (
                id, {", ".join(columns)}, updated_at
            )
            VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET
                {assignments},
                updated_at = excluded.updated_at
            """,
            (_SINGLETON_ID, *values.values(), updated_at),
        )
        self._insert_change_event(
            settings_group=settings_group,
            changed_fields=diff_changed_fields(current=current, new_values=dict(values)),
            created_at=updated_at,
        )
        commit_unit_of_work(self._conn)

    def upsert_throttle_settings(
        self,
        *,
        runtime_max_trades_per_day: int | None,
        runtime_max_trades_per_minute: int | None,
        updated_at: str,
    ) -> None:
        self._upsert_group(
            values={
                "runtime_max_trades_per_day": runtime_max_trades_per_day,
                "runtime_max_trades_per_minute": runtime_max_trades_per_minute,
            },
            settings_group=GLOBAL_SETTINGS_GROUP_THROTTLE,
            updated_at=updated_at,
        )

    def upsert_evaluation_settings(
        self,
        *,
        backtest_trade_count_for_full_confidence: int,
        backtest_snapshot_count_for_full_confidence: int,
        paper_live_snapshot_count_for_full_confidence: int,
        backtest_trade_confidence_weight: float,
        backtest_snapshot_confidence_weight: float,
        backtest_evidence_weight: float,
        paper_live_evidence_weight: float,
        updated_at: str,
    ) -> None:
        self._upsert_group(
            values={
                "evaluation_backtest_trade_count_for_full_confidence": backtest_trade_count_for_full_confidence,
                "evaluation_backtest_snapshot_count_for_full_confidence": backtest_snapshot_count_for_full_confidence,
                "evaluation_paper_live_snapshot_count_for_full_confidence": paper_live_snapshot_count_for_full_confidence,
                "evaluation_backtest_trade_confidence_weight": backtest_trade_confidence_weight,
                "evaluation_backtest_snapshot_confidence_weight": backtest_snapshot_confidence_weight,
                "evaluation_backtest_evidence_weight": backtest_evidence_weight,
                "evaluation_paper_live_evidence_weight": paper_live_evidence_weight,
            },
            settings_group=GLOBAL_SETTINGS_GROUP_EVALUATION,
            updated_at=updated_at,
        )

    def upsert_promotion_settings(
        self,
        *,
        min_research_backtest_trade_count: int,
        min_research_backtest_snapshot_count: int,
        min_research_backtest_return_pct: float,
        min_research_max_drawdown_pct: float,
        min_research_walk_forward_average_return_pct: float,
        min_live_paper_snapshot_count: int,
        min_live_overall_confidence: float,
        updated_at: str,
    ) -> None:
        self._upsert_group(
            values={
                "promotion_min_research_backtest_trade_count": min_research_backtest_trade_count,
                "promotion_min_research_backtest_snapshot_count": min_research_backtest_snapshot_count,
                "promotion_min_research_backtest_return_pct": min_research_backtest_return_pct,
                "promotion_min_research_max_drawdown_pct": min_research_max_drawdown_pct,
                "promotion_min_research_walk_forward_average_return_pct": min_research_walk_forward_average_return_pct,
                "promotion_min_live_paper_snapshot_count": min_live_paper_snapshot_count,
                "promotion_min_live_overall_confidence": min_live_overall_confidence,
            },
            settings_group=GLOBAL_SETTINGS_GROUP_PROMOTION,
            updated_at=updated_at,
        )
