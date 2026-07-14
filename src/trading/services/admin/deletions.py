from __future__ import annotations

from collections.abc import Sequence
import sqlite3

from common.coercion import coerce_int
from trading.domain.exceptions import NotFoundError
from trading.repositories.accounts import AccountRepository
from trading.repositories.admin_deletions import (
    count_child_rows_for_account_ids,
    fetch_row_count,
)


DELETE_COUNT_KEYS = (
    "accounts",
    "trades",
    "orders",
    "order_fills",
    "equity_snapshots",
    "backtest_runs",
    "backtest_trades",
    "backtest_equity_snapshots",
    "walk_forward_groups",
    "walk_forward_group_runs",
    "promotion_reviews",
    "promotion_review_events",
    "risk_snapshots",
    "risk_decisions",
)

# Tables keyed directly to accounts.id; counted with a plain account_id filter.
_ACCOUNT_KEYED_COUNT_TABLES = (
    "trades",
    "orders",
    "backtest_runs",
    "walk_forward_groups",
    "promotion_reviews",
    "risk_snapshots",
    "risk_decisions",
)

# Child tables counted through their owning parent (see admin_deletions).
_CHILD_COUNT_TABLES = (
    "order_fills",
    "equity_snapshots",
    "backtest_trades",
    "backtest_equity_snapshots",
    "walk_forward_group_runs",
    "promotion_review_events",
)


def _resolve_delete_targets(
    conn: sqlite3.Connection,
    names: list[str],
    delete_all: bool,
) -> list[dict[str, object]]:
    repo = AccountRepository(conn)
    if delete_all:
        records = repo.fetch_all()
    else:
        records = repo.fetch_by_names(tuple(names))
        found = {record.name for record in records}
        missing = [name for name in names if name not in found]
        if missing:
            missing_text = ", ".join(missing)
            raise NotFoundError(f"Accounts not found: {missing_text}")

    return [{"id": record.id, "name": record.name} for record in records]


def _empty_delete_counts() -> dict[str, int]:
    return {key: 0 for key in DELETE_COUNT_KEYS}


def iter_delete_count_items(counts: dict[str, int]) -> list[tuple[str, int]]:
    return [(key, int(counts.get(key, 0))) for key in DELETE_COUNT_KEYS]


def _collect_required_ids(
    rows: Sequence[dict[str, object]],
    *,
    key: str,
    label: str,
) -> tuple[int, ...]:
    ids = tuple(account_id for row in rows if (account_id := coerce_int(row[key])) is not None)
    if len(ids) != len(rows):
        raise ValueError(f"Unexpected non-integer {label} id in delete target set.")
    return ids


def delete_accounts(
    conn: sqlite3.Connection,
    *,
    account_names: list[str],
    delete_all: bool,
    dry_run: bool,
) -> dict[str, int]:
    targets = _resolve_delete_targets(conn, account_names, delete_all)
    if not targets:
        return _empty_delete_counts()

    account_ids = _collect_required_ids(targets, key="id", label="account")

    counts = _empty_delete_counts()
    counts["accounts"] = len(targets)
    for table in _ACCOUNT_KEYED_COUNT_TABLES:
        counts[table] = fetch_row_count(conn, table, "account_id", account_ids)
    for table in _CHILD_COUNT_TABLES:
        counts[table] = count_child_rows_for_account_ids(conn, table, account_ids)

    if dry_run:
        return counts

    # One atomic statement: ON DELETE CASCADE removes every account-owned row
    # (books, orders, fills, snapshots, research, governance, risk).
    AccountRepository(conn).delete_by_ids(account_ids)
    return counts
