from __future__ import annotations

import datetime as dt
import sqlite3

from trading.repositories.book_bridge import strategy_id_for_label

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
    """Book-keyed rotation decisions.

    Storage uses strategy-id FKs and first-class score columns; strategy
    labels are bridged to strategies rows via book_bridge.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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

    def fetch_latest_for_book(self, *, book_id: int) -> sqlite3.Row | None:
        rows = self._conn.execute(
            _LEGACY_ROW_SELECT + " ORDER BY d.decision_time DESC, d.id DESC LIMIT 1",
            (None, int(book_id)),
        ).fetchall()
        return rows[0] if rows else None

    def fetch_for_book(self, *, book_id: int, limit: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            _LEGACY_ROW_SELECT + " ORDER BY d.decision_time DESC, d.id DESC LIMIT ?",
            (None, int(book_id), int(limit)),
        ).fetchall()

    def fetch_for_book_on_date(self, *, book_id: int, report_date: str) -> list[sqlite3.Row]:
        next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
        return self._conn.execute(
            _LEGACY_ROW_SELECT
            + " AND d.decision_time >= ? AND d.decision_time < ? ORDER BY d.decision_time ASC, d.id ASC",
            (None, int(book_id), report_date, next_date),
        ).fetchall()

    def fetch_selected_strategy_timeline(self, *, book_id: int) -> list[tuple[str, str | None, str | None]]:
        """Return the book's decision log as ``(decision_time, incumbent, selected)`` rows, oldest first.

        Every decision (hold or rotate) records the strategy active after it
        (``selected``) and the one active before it (``incumbent``), so the ordered
        log reconstructs the book's active-strategy timeline — the substrate for
        strategy-isolated paper-live evidence now that rotation episodes are retired.
        """
        rows = self._conn.execute(
            """
            SELECT
                d.decision_time AS decision_time,
                si.strategy_key AS incumbent_strategy,
                ss.strategy_key AS selected_strategy
            FROM rotation_decisions d
            LEFT JOIN strategies si ON si.id = d.incumbent_strategy_id
            LEFT JOIN strategies ss ON ss.id = d.selected_strategy_id
            WHERE d.book_id = ?
            ORDER BY d.decision_time ASC, d.id ASC
            """,
            (int(book_id),),
        ).fetchall()
        return [
            (
                str(row["decision_time"]),
                str(row["incumbent_strategy"]) if row["incumbent_strategy"] is not None else None,
                str(row["selected_strategy"]) if row["selected_strategy"] is not None else None,
            )
            for row in rows
        ]

    def fetch_latest_rotate_action_for_book(self, *, book_id: int) -> sqlite3.Row | None:
        """Return the book's most recent 'rotate' decision (book-native cooldown source)."""
        return self._conn.execute(
            """
            SELECT d.decision_time AS decision_time
            FROM rotation_decisions d
            WHERE d.book_id = ? AND d.rotation_action = 'rotate'
            ORDER BY d.decision_time DESC, d.id DESC
            LIMIT 1
            """,
            (int(book_id),),
        ).fetchone()
