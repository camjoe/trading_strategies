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

# Child tables reachable only through an owning parent keyed to accounts. Used
# by deletion-count reporting; the rows themselves are removed by the
# ON DELETE CASCADE chain when the account row is deleted.
_CHILD_COUNT_PREDICATES = {
    "order_fills": "order_id IN (SELECT id FROM orders WHERE account_id IN ({placeholders}))",
    "equity_snapshots": "book_id IN (SELECT id FROM books WHERE account_id IN ({placeholders}))",
    "backtest_trades": "run_id IN (SELECT id FROM backtest_runs WHERE account_id IN ({placeholders}))",
    "backtest_equity_snapshots": "run_id IN (SELECT id FROM backtest_runs WHERE account_id IN ({placeholders}))",
    "walk_forward_group_runs": "group_id IN (SELECT id FROM walk_forward_groups WHERE account_id IN ({placeholders}))",
    "promotion_review_events": "review_id IN (SELECT id FROM promotion_reviews WHERE account_id IN ({placeholders}))",
}


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

    def fetch_by_names(self, names: tuple[str, ...]) -> list[AccountRecord]:
        if not names:
            return []
        placeholders = ", ".join("?" for _ in names)
        rows = self._conn.execute(
            f"SELECT * FROM accounts WHERE name IN ({placeholders}) ORDER BY name ASC",
            names,
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

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

    def delete_by_ids(self, account_ids: tuple[int, ...]) -> None:
        """Delete accounts in one statement; ON DELETE CASCADE removes all account-owned rows."""
        if not account_ids:
            return
        placeholders = ", ".join("?" for _ in account_ids)
        self._conn.execute(f"DELETE FROM accounts WHERE id IN ({placeholders})", account_ids)
        self._conn.commit()

    def fetch_owned_row_count(self, table: str, account_ids: tuple[int, ...]) -> int:
        """Count rows in a table keyed directly to accounts.id via account_id."""
        placeholders = ", ".join("?" for _ in account_ids)
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE account_id IN ({placeholders})",
            account_ids,
        ).fetchone()
        if row is None:
            return 0
        n = row["n"]
        if not isinstance(n, int):
            raise ValueError(f"Unexpected non-integer count from table '{table}'.")
        return n

    def fetch_child_row_count(self, table: str, account_ids: tuple[int, ...]) -> int:
        """Count rows in a child table reachable only through an owning parent."""
        placeholders = ", ".join("?" for _ in account_ids)
        predicate = _CHILD_COUNT_PREDICATES[table].format(placeholders=placeholders)
        row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {predicate}", account_ids).fetchone()
        return int(row["n"]) if row is not None else 0
