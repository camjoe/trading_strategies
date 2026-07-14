from __future__ import annotations

from collections.abc import Sequence
import sqlite3

from common.coercion import coerce_int
from trading.domain.exceptions import NotFoundError
from trading.repositories.accounts import AccountRepository


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
    if dry_run:
        targets = _resolve_delete_targets(conn, account_names, delete_all)
        if not targets:
            return _empty_delete_counts()
        account_ids = _collect_required_ids(targets, key="id", label="account")
        repo = AccountRepository(conn)
        counts = _empty_delete_counts()
        counts["accounts"] = len(targets)
        counts.update(repo.fetch_delete_counts(account_ids))
        return counts

    if conn.in_transaction:
        raise RuntimeError("Cannot delete accounts while the connection has an open transaction.")

    # Acquire the write reservation before counting so the reported rows cannot
    # change before the cascade-backed delete commits.
    conn.execute("BEGIN IMMEDIATE")
    try:
        targets = _resolve_delete_targets(conn, account_names, delete_all)
        if not targets:
            conn.commit()
            return _empty_delete_counts()
        account_ids = _collect_required_ids(targets, key="id", label="account")
        repo = AccountRepository(conn)
        counts = _empty_delete_counts()
        counts["accounts"] = len(targets)
        counts.update(repo.fetch_delete_counts(account_ids))
        repo.delete_by_ids(account_ids, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts
