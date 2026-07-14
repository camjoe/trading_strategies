from __future__ import annotations

import sqlite3
from dataclasses import astuple

from trading.models import AccountInsert, AccountRecord

_ACCOUNT_INSERT_COLUMNS = (
    "name",
    "account_kind",
    "strategy",
    "initial_cash",
    "created_at",
    "benchmark_ticker",
    "descriptive_name",
    "goal_min_return_pct",
    "goal_max_return_pct",
    "goal_period",
    "learning_enabled",
    "risk_policy",
    "stop_loss_pct",
    "take_profit_pct",
    "trade_size_pct",
    "max_position_pct",
    "instrument_mode",
    "option_strike_offset_pct",
    "option_min_dte",
    "option_max_dte",
    "option_type",
    "target_delta_min",
    "target_delta_max",
    "max_premium_per_trade",
    "max_contracts_per_trade",
    "iv_rank_min",
    "iv_rank_max",
    "roll_dte_threshold",
    "profit_take_pct",
    "max_loss_pct",
    "trade_universes",
)
_ACCOUNT_INSERT_SQL = (
    f"INSERT INTO accounts ({', '.join(_ACCOUNT_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _ACCOUNT_INSERT_COLUMNS)})"
)


class AccountRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> AccountRecord:
        return AccountRecord.from_mapping(dict(row))

    def fetch_all(self) -> list[AccountRecord]:
        rows = self._conn.execute("SELECT * FROM accounts ORDER BY name").fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_by_name(self, name: str) -> AccountRecord | None:
        row = self._conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_listing(self) -> list[AccountRecord]:
        rows = self._conn.execute("SELECT * FROM accounts ORDER BY strategy ASC, name ASC").fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_names(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
        return [str(row["name"]) for row in rows]

    def insert(self, account: AccountInsert) -> None:
        self._conn.execute(_ACCOUNT_INSERT_SQL, astuple(account))
        self._conn.commit()

    def update(self, *, account_id: int, updates: list[str], params: list[object]) -> None:
        query_params = [*params, account_id]
        self._conn.execute(
            f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?",
            tuple(query_params),
        )
        self._conn.commit()

    def update_benchmark(self, *, account_id: int, benchmark_ticker: str) -> None:
        self._conn.execute(
            "UPDATE accounts SET benchmark_ticker = ? WHERE id = ?",
            (benchmark_ticker, account_id),
        )
        self._conn.commit()

    def delete_by_name(self, account_name: str) -> AccountRecord | None:
        """Delete one account and return it; database cascades remove owned rows."""
        row = self._conn.execute(
            "DELETE FROM accounts WHERE name = ? RETURNING *",
            (account_name,),
        ).fetchone()
        self._conn.commit()
        return self._row_to_record(row) if row is not None else None
