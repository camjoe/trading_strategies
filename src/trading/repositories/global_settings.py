from __future__ import annotations

import sqlite3

from trading.models.settings import (
    GLOBAL_SETTINGS_GROUP_EVALUATION,
    GLOBAL_SETTINGS_GROUP_PROMOTION,
    GLOBAL_SETTINGS_GROUP_THROTTLE,
    GlobalSettingsChangeEvent,
    GlobalSettingsRecord,
)
from trading.persistence.change_events import diff_changed_fields, json_object_dumps, row_json_object
from trading.persistence.unit_of_work import commit_unit_of_work


class GlobalSettingsRepository:
    """Persist optional operator overrides for global operational policy."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> GlobalSettingsRecord:
        return GlobalSettingsRecord.from_mapping(dict(row))

    def fetch(self) -> GlobalSettingsRecord | None:
        row = self._conn.execute("SELECT * FROM global_settings WHERE id = 1").fetchone()
        return self._row_to_record(row) if row is not None else None

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
            (settings_group, json_object_dumps(changed_fields), created_at),
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
        return [
            GlobalSettingsChangeEvent(
                id=int(row["id"]),
                settings_group=str(row["settings_group"]),
                changed_fields=row_json_object(row, "changed_fields"),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def upsert_throttle_settings(
        self,
        *,
        runtime_max_trades_per_day: int | None,
        runtime_max_trades_per_minute: int | None,
        updated_at: str,
    ) -> None:
        current = self.fetch()
        new_values = {
            "runtime_max_trades_per_day": runtime_max_trades_per_day,
            "runtime_max_trades_per_minute": runtime_max_trades_per_minute,
        }
        self._conn.execute(
            """
            INSERT INTO global_settings (
                id,
                runtime_max_trades_per_day,
                runtime_max_trades_per_minute,
                updated_at
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                runtime_max_trades_per_day = excluded.runtime_max_trades_per_day,
                runtime_max_trades_per_minute = excluded.runtime_max_trades_per_minute,
                updated_at = excluded.updated_at
            """,
            (runtime_max_trades_per_day, runtime_max_trades_per_minute, updated_at),
        )
        changed = diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            settings_group=GLOBAL_SETTINGS_GROUP_THROTTLE, changed_fields=changed, created_at=updated_at
        )
        commit_unit_of_work(self._conn)

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
        current = self.fetch()
        new_values = {
            "evaluation_backtest_trade_count_for_full_confidence": backtest_trade_count_for_full_confidence,
            "evaluation_backtest_snapshot_count_for_full_confidence": backtest_snapshot_count_for_full_confidence,
            "evaluation_paper_live_snapshot_count_for_full_confidence": paper_live_snapshot_count_for_full_confidence,
            "evaluation_backtest_trade_confidence_weight": backtest_trade_confidence_weight,
            "evaluation_backtest_snapshot_confidence_weight": backtest_snapshot_confidence_weight,
            "evaluation_backtest_evidence_weight": backtest_evidence_weight,
            "evaluation_paper_live_evidence_weight": paper_live_evidence_weight,
        }
        self._conn.execute(
            """
            INSERT INTO global_settings (
                id,
                evaluation_backtest_trade_count_for_full_confidence,
                evaluation_backtest_snapshot_count_for_full_confidence,
                evaluation_paper_live_snapshot_count_for_full_confidence,
                evaluation_backtest_trade_confidence_weight,
                evaluation_backtest_snapshot_confidence_weight,
                evaluation_backtest_evidence_weight,
                evaluation_paper_live_evidence_weight,
                updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                evaluation_backtest_trade_count_for_full_confidence
                    = excluded.evaluation_backtest_trade_count_for_full_confidence,
                evaluation_backtest_snapshot_count_for_full_confidence
                    = excluded.evaluation_backtest_snapshot_count_for_full_confidence,
                evaluation_paper_live_snapshot_count_for_full_confidence
                    = excluded.evaluation_paper_live_snapshot_count_for_full_confidence,
                evaluation_backtest_trade_confidence_weight = excluded.evaluation_backtest_trade_confidence_weight,
                evaluation_backtest_snapshot_confidence_weight = excluded.evaluation_backtest_snapshot_confidence_weight,
                evaluation_backtest_evidence_weight = excluded.evaluation_backtest_evidence_weight,
                evaluation_paper_live_evidence_weight = excluded.evaluation_paper_live_evidence_weight,
                updated_at = excluded.updated_at
            """,
            (
                backtest_trade_count_for_full_confidence,
                backtest_snapshot_count_for_full_confidence,
                paper_live_snapshot_count_for_full_confidence,
                backtest_trade_confidence_weight,
                backtest_snapshot_confidence_weight,
                backtest_evidence_weight,
                paper_live_evidence_weight,
                updated_at,
            ),
        )
        changed = diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            settings_group=GLOBAL_SETTINGS_GROUP_EVALUATION, changed_fields=changed, created_at=updated_at
        )
        commit_unit_of_work(self._conn)

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
        current = self.fetch()
        new_values = {
            "promotion_min_research_backtest_trade_count": min_research_backtest_trade_count,
            "promotion_min_research_backtest_snapshot_count": min_research_backtest_snapshot_count,
            "promotion_min_research_backtest_return_pct": min_research_backtest_return_pct,
            "promotion_min_research_max_drawdown_pct": min_research_max_drawdown_pct,
            "promotion_min_research_walk_forward_average_return_pct": min_research_walk_forward_average_return_pct,
            "promotion_min_live_paper_snapshot_count": min_live_paper_snapshot_count,
            "promotion_min_live_overall_confidence": min_live_overall_confidence,
        }
        self._conn.execute(
            """
            INSERT INTO global_settings (
                id,
                promotion_min_research_backtest_trade_count,
                promotion_min_research_backtest_snapshot_count,
                promotion_min_research_backtest_return_pct,
                promotion_min_research_max_drawdown_pct,
                promotion_min_research_walk_forward_average_return_pct,
                promotion_min_live_paper_snapshot_count,
                promotion_min_live_overall_confidence,
                updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                promotion_min_research_backtest_trade_count = excluded.promotion_min_research_backtest_trade_count,
                promotion_min_research_backtest_snapshot_count = excluded.promotion_min_research_backtest_snapshot_count,
                promotion_min_research_backtest_return_pct = excluded.promotion_min_research_backtest_return_pct,
                promotion_min_research_max_drawdown_pct = excluded.promotion_min_research_max_drawdown_pct,
                promotion_min_research_walk_forward_average_return_pct
                    = excluded.promotion_min_research_walk_forward_average_return_pct,
                promotion_min_live_paper_snapshot_count = excluded.promotion_min_live_paper_snapshot_count,
                promotion_min_live_overall_confidence = excluded.promotion_min_live_overall_confidence,
                updated_at = excluded.updated_at
            """,
            (
                min_research_backtest_trade_count,
                min_research_backtest_snapshot_count,
                min_research_backtest_return_pct,
                min_research_max_drawdown_pct,
                min_research_walk_forward_average_return_pct,
                min_live_paper_snapshot_count,
                min_live_overall_confidence,
                updated_at,
            ),
        )
        changed = diff_changed_fields(current=current, new_values=new_values)
        self._insert_change_event(
            settings_group=GLOBAL_SETTINGS_GROUP_PROMOTION, changed_fields=changed, created_at=updated_at
        )
        commit_unit_of_work(self._conn)
