from __future__ import annotations

import datetime as dt
import sqlite3

from trading.repositories.book_bridge import book_id_for_sleeve, strategy_id_for_label

# Reads join strategies to keep emitting the legacy label columns
# (incumbent_strategy / challenger_strategy / selected_strategy) plus the
# caller's sleeve_id, so raw-row consumers are unchanged during the window.
_LEGACY_ROW_SELECT = """
SELECT
    d.*,
    ? AS sleeve_id,
    NULL AS param_set_id,
    si.strategy_key AS incumbent_strategy,
    sc.strategy_key AS challenger_strategy,
    ss.strategy_key AS selected_strategy
FROM rotation_decisions d
LEFT JOIN strategies si ON si.id = d.incumbent_strategy_id
LEFT JOIN strategies sc ON sc.id = d.challenger_strategy_id
LEFT JOIN strategies ss ON ss.id = d.selected_strategy_id
WHERE d.book_id = ?
"""


class RotationDecisionRepository:
    """Book-keyed rotation decisions with the legacy sleeve access path.

    Storage follows the clean schema (strategy-id FKs; D6 score columns).
    Legacy sleeve ids and strategy labels are bridged via book_bridge until
    P4's unified rotation service owns this table.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        sleeve_id: int,
        decision_time: str,
        incumbent_strategy: str | None,
        challenger_strategy: str | None,
        selected_strategy: str | None,
        rotation_action: str,
        cooldown_active: int,
        score_components_json: str,
        gate_results_json: str,
        decision_reason: str | None,
        config_version: str | None,
        param_set_id: int | None = None,
        decision_score: float | None = None,
        decision_confidence: float | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        realized_pnl_delta: float | None = None,
        created_at: str,
    ) -> int:
        # param_set_id is retired (D5: the strategy row carries its knobs);
        # accepted for call compatibility until P4 rewires the writers.
        del param_set_id
        book_id = book_id_for_sleeve(self._conn, int(sleeve_id), create=True)
        return self.insert_for_book(
            book_id=book_id,
            decision_time=decision_time,
            incumbent_strategy=incumbent_strategy,
            challenger_strategy=challenger_strategy,
            selected_strategy=selected_strategy,
            rotation_action=rotation_action,
            cooldown_active=cooldown_active,
            score_components_json=score_components_json,
            gate_results_json=gate_results_json,
            decision_reason=decision_reason,
            config_version=config_version,
            decision_score=decision_score,
            decision_confidence=decision_confidence,
            window_start=window_start,
            window_end=window_end,
            realized_pnl_delta=realized_pnl_delta,
            created_at=created_at,
        )

    def insert_for_book(
        self,
        *,
        book_id: int,
        decision_time: str,
        incumbent_strategy: str | None,
        challenger_strategy: str | None,
        selected_strategy: str | None,
        rotation_action: str,
        cooldown_active: int,
        score_components_json: str,
        gate_results_json: str,
        decision_reason: str | None,
        config_version: str | None,
        decision_score: float | None = None,
        decision_confidence: float | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        realized_pnl_delta: float | None = None,
        created_at: str,
    ) -> int:
        """Record a rotation decision keyed directly on a book.

        The book-native writer used by the unified rotation path (a plain account's
        default book or a sleeve's bridging book). ``insert`` layers the legacy
        ``sleeve_id`` → ``book_id`` bridge on top of this.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO rotation_decisions (
                book_id,
                decision_time,
                incumbent_strategy_id,
                challenger_strategy_id,
                selected_strategy_id,
                rotation_action,
                cooldown_active,
                decision_score,
                decision_confidence,
                score_components_json,
                gate_results_json,
                decision_reason,
                config_version,
                window_start,
                window_end,
                realized_pnl_delta,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                decision_time,
                strategy_id_for_label(self._conn, incumbent_strategy, now_iso=created_at),
                strategy_id_for_label(self._conn, challenger_strategy, now_iso=created_at),
                strategy_id_for_label(self._conn, selected_strategy, now_iso=created_at),
                rotation_action,
                int(cooldown_active),
                decision_score,
                decision_confidence,
                score_components_json,
                gate_results_json,
                decision_reason,
                config_version,
                window_start,
                window_end,
                realized_pnl_delta,
                created_at,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected rotation_decisions id after insert.")
        return int(cursor.lastrowid)

    def _rows_for_sleeve(self, *, sleeve_id: int, suffix: str, params: tuple) -> list[sqlite3.Row]:
        book_id = book_id_for_sleeve(self._conn, int(sleeve_id), create=False)
        if book_id is None:
            return []
        return self._conn.execute(
            _LEGACY_ROW_SELECT + suffix,
            (int(sleeve_id), int(book_id), *params),
        ).fetchall()

    def fetch_latest(self, *, sleeve_id: int) -> sqlite3.Row | None:
        rows = self._rows_for_sleeve(
            sleeve_id=sleeve_id,
            suffix=" ORDER BY d.decision_time DESC, d.id DESC LIMIT 1",
            params=(),
        )
        return rows[0] if rows else None

    def fetch_for_sleeve(self, *, sleeve_id: int, limit: int) -> list[sqlite3.Row]:
        return self._rows_for_sleeve(
            sleeve_id=sleeve_id,
            suffix=" ORDER BY d.decision_time DESC, d.id DESC LIMIT ?",
            params=(int(limit),),
        )

    def fetch_for_sleeve_on_date(self, *, sleeve_id: int, report_date: str) -> list[sqlite3.Row]:
        next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
        return self._rows_for_sleeve(
            sleeve_id=sleeve_id,
            suffix=" AND d.decision_time >= ? AND d.decision_time < ? ORDER BY d.decision_time ASC, d.id ASC",
            params=(report_date, next_date),
        )

    def fetch_latest_rotate_action(self, *, sleeve_id: int) -> sqlite3.Row | None:
        """Return the most recent decision where rotation_action = 'rotate'."""
        rows = self._rows_for_sleeve(
            sleeve_id=sleeve_id,
            suffix=" AND d.rotation_action = 'rotate' ORDER BY d.decision_time DESC, d.id DESC LIMIT 1",
            params=(),
        )
        return rows[0] if rows else None
