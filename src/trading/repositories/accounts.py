from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models import AccountInsert, AccountRecord
from trading.persistence.money_columns import encode_columns, encode_money
from trading.persistence.unit_of_work import commit_unit_of_work

_ACCOUNT_INSERT_COLUMNS = (
    "name",
    "initial_cash",
    "created_at",
    "updated_at",
    "benchmark_ticker",
    "descriptive_name",
)

# Money columns stored as integer minor units; encoded on write, decoded on read.
_ACCOUNT_MONEY_COLUMNS = frozenset({"initial_cash"})
_NO_QUANTITY_COLUMNS: frozenset[str] = frozenset()
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

    def fetch_by_id(self, *, account_id: int) -> AccountRecord | None:
        row = self._conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return AccountRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_by_name(self, *, account_name: str) -> AccountRecord | None:
        row = self._conn.execute("SELECT * FROM accounts WHERE name = ?", (account_name,)).fetchone()
        return AccountRecord.from_mapping(dict(row)) if row is not None else None

    def insert(self, account: AccountInsert) -> None:
        self._conn.execute(
            _ACCOUNT_INSERT_SQL,
            (
                account.name,
                encode_money(account.initial_cash),
                account.created_at,
                account.updated_at,
                account.benchmark_ticker,
                account.descriptive_name,
            ),
        )
        commit_unit_of_work(self._conn)

    def update(self, *, account_id: int, values: Mapping[str, object], updated_at: str) -> None:
        """Write ``values`` as a partial column update to one account; no-op when empty."""
        if not values:
            return
        encoded = encode_columns(values, money_columns=_ACCOUNT_MONEY_COLUMNS, quantity_columns=_NO_QUANTITY_COLUMNS)
        assignments = ", ".join(f"{column} = ?" for column in encoded)
        self._conn.execute(
            f"UPDATE accounts SET {assignments}, updated_at = ? WHERE id = ?",
            (*encoded.values(), updated_at, account_id),
        )
        commit_unit_of_work(self._conn)

    def delete_by_name(self, *, account_name: str) -> AccountRecord | None:
        """Delete one account and return it; database cascades remove owned rows."""
        row = self._conn.execute(
            "DELETE FROM accounts WHERE name = ? RETURNING *",
            (account_name,),
        ).fetchone()
        commit_unit_of_work(self._conn)
        return AccountRecord.from_mapping(dict(row)) if row is not None else None
