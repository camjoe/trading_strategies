from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import astuple

from trading.models import AccountInsert, AccountRecord
from trading.persistence.unit_of_work import commit_unit_of_work

_ACCOUNT_INSERT_COLUMNS = (
    "name",
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

    def fetch_all(self) -> list[AccountRecord]:
        rows = self._conn.execute("SELECT * FROM accounts ORDER BY name ASC").fetchall()
        return [AccountRecord.from_mapping(dict(row)) for row in rows]

    def fetch_by_name(self, name: str) -> AccountRecord | None:
        row = self._conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
        return AccountRecord.from_mapping(dict(row)) if row is not None else None

    def insert(self, account: AccountInsert) -> None:
        self._conn.execute(_ACCOUNT_INSERT_SQL, astuple(account))
        commit_unit_of_work(self._conn)

    def update(self, *, account_id: int, values: Mapping[str, object], updated_at: str) -> None:
        """Write ``values`` as a partial column update to one account; no-op when empty."""
        if not values:
            return
        assignments = ", ".join(f"{column} = ?" for column in values)
        self._conn.execute(
            f"UPDATE accounts SET {assignments}, updated_at = ? WHERE id = ?",
            (*values.values(), updated_at, account_id),
        )
        commit_unit_of_work(self._conn)

    def delete_by_name(self, account_name: str) -> AccountRecord | None:
        """Delete one account and return it; database cascades remove owned rows."""
        row = self._conn.execute(
            "DELETE FROM accounts WHERE name = ? RETURNING *",
            (account_name,),
        ).fetchone()
        commit_unit_of_work(self._conn)
        return AccountRecord.from_mapping(dict(row)) if row is not None else None
