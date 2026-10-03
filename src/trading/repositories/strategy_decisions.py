from __future__ import annotations

import sqlite3
from dataclasses import fields

from trading.models.advisor import (
    OUTCOME_STATUS_PENDING,
    StrategyDecisionInsert,
    StrategyDecisionOutcome,
    StrategyDecisionRecord,
)
from trading.persistence.unit_of_work import commit_unit_of_work

_DECISION_COLUMNS = tuple(field.name for field in fields(StrategyDecisionInsert))
_INSERT_SQL = (
    f"INSERT INTO strategy_decisions ({', '.join(_DECISION_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _DECISION_COLUMNS)})"
)
_OUTCOME_COLUMNS = tuple(field.name for field in fields(StrategyDecisionOutcome))
_UPDATE_OUTCOME_SQL = (
    f"UPDATE strategy_decisions SET {', '.join(f'{column} = ?' for column in _OUTCOME_COLUMNS)} WHERE id = ?"
)


class StrategyDecisionRepository:
    """SQL access for the strategy_decisions ledger.

    The only writers are `insert` and `update_outcome`: decision columns are write-once
    (a table trigger rejects any update to them), so there is no general update.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, decision: StrategyDecisionInsert) -> int:
        cursor = self._conn.execute(
            _INSERT_SQL,
            tuple(getattr(decision, column) for column in _DECISION_COLUMNS),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def update_outcome(self, *, strategy_decision_id: int, outcome: StrategyDecisionOutcome) -> bool:
        """Write the outcome columns; return False when no row has that id."""
        cursor = self._conn.execute(
            _UPDATE_OUTCOME_SQL,
            (*(getattr(outcome, column) for column in _OUTCOME_COLUMNS), strategy_decision_id),
        )
        commit_unit_of_work(self._conn)
        return cursor.rowcount > 0

    def fetch(self, *, strategy_decision_id: int) -> StrategyDecisionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM strategy_decisions WHERE id = ?",
            (strategy_decision_id,),
        ).fetchone()
        return StrategyDecisionRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_recent(self, *, account_id: int, limit: int = 50) -> list[StrategyDecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM strategy_decisions WHERE account_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (account_id, limit),
        ).fetchall()
        return [StrategyDecisionRecord.from_mapping(dict(row)) for row in rows]

    def fetch_pending(self, *, account_id: int | None = None) -> list[StrategyDecisionRecord]:
        """Decisions not yet scored, oldest first; all accounts when ``account_id`` is None."""
        if account_id is None:
            rows = self._conn.execute(
                "SELECT * FROM strategy_decisions WHERE outcome_status = ? ORDER BY created_at ASC, id ASC",
                (OUTCOME_STATUS_PENDING,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM strategy_decisions WHERE outcome_status = ? AND account_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (OUTCOME_STATUS_PENDING, account_id),
            ).fetchall()
        return [StrategyDecisionRecord.from_mapping(dict(row)) for row in rows]

    def fetch_scored(self, *, account_id: int | None = None) -> list[StrategyDecisionRecord]:
        """Decisions scoring has finished with (measured or inconclusive), oldest first."""
        if account_id is None:
            rows = self._conn.execute(
                "SELECT * FROM strategy_decisions WHERE outcome_status <> ? ORDER BY created_at ASC, id ASC",
                (OUTCOME_STATUS_PENDING,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM strategy_decisions WHERE outcome_status <> ? AND account_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (OUTCOME_STATUS_PENDING, account_id),
            ).fetchall()
        return [StrategyDecisionRecord.from_mapping(dict(row)) for row in rows]
