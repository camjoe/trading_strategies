from __future__ import annotations

import sqlite3
from dataclasses import astuple

from trading.models import AccountInsert, AccountRecord
from trading.repositories.unit_of_work import commit_unit_of_work

_ACCOUNT_INSERT_COLUMNS = (
    "name",
    "account_kind",
    "initial_cash",
    "created_at",
    "updated_at",
    "benchmark_ticker",
    "descriptive_name",
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
        rows = self._conn.execute("SELECT * FROM accounts ORDER BY name ASC").fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_names(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
        return [str(row["name"]) for row in rows]

    def insert(self, account: AccountInsert) -> None:
        self._conn.execute(_ACCOUNT_INSERT_SQL, astuple(account))
        commit_unit_of_work(self._conn)

    def update(self, *, account_id: int, updates: list[str], params: list[object], updated_at: str) -> None:
        query_params = [*params, updated_at, account_id]
        self._conn.execute(
            f"UPDATE accounts SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
            tuple(query_params),
        )
        commit_unit_of_work(self._conn)

    def update_benchmark(self, *, account_id: int, benchmark_ticker: str, updated_at: str) -> None:
        self._conn.execute(
            "UPDATE accounts SET benchmark_ticker = ?, updated_at = ? WHERE id = ?",
            (benchmark_ticker, updated_at, account_id),
        )
        commit_unit_of_work(self._conn)

    def delete_by_name(self, account_name: str) -> AccountRecord | None:
        """Delete one account and return it; database cascades remove owned rows."""
        row = self._conn.execute(
            "DELETE FROM accounts WHERE name = ? RETURNING *",
            (account_name,),
        ).fetchone()
        commit_unit_of_work(self._conn)
        return self._row_to_record(row) if row is not None else None
