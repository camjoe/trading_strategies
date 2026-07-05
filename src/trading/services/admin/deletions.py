from __future__ import annotations

from collections.abc import Sequence
import sqlite3

from common.coercion import coerce_int
from trading.domain.exceptions import NotFoundError
from trading.repositories.accounts import AccountRepository
from trading.repositories.admin_deletions import (
    count_equity_snapshots_for_account_ids,
    delete_accounts_by_ids,
    delete_backtest_equity_snapshots_by_run_ids,
    delete_backtest_runs_by_account_ids,
    delete_backtest_trades_by_run_ids,
    delete_equity_snapshots_by_account_ids,
    delete_promotion_review_events_by_review_ids,
    delete_promotion_reviews_by_account_ids,
    delete_trades_by_account_ids,
    delete_walk_forward_group_runs_by_group_ids,
    delete_walk_forward_groups_by_account_ids,
    fetch_backtest_run_ids_for_account_ids,
    fetch_promotion_review_ids_for_account_ids,
    fetch_row_count,
    fetch_walk_forward_group_ids_for_account_ids,
)


DELETE_COUNT_KEYS = (
    "accounts",
    "trades",
    "equity_snapshots",
    "backtest_runs",
    "backtest_trades",
    "backtest_equity_snapshots",
    "walk_forward_groups",
    "walk_forward_group_runs",
    "promotion_reviews",
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

    run_ids = fetch_backtest_run_ids_for_account_ids(conn, account_ids)
    walk_forward_group_ids = fetch_walk_forward_group_ids_for_account_ids(conn, account_ids)
    review_ids = fetch_promotion_review_ids_for_account_ids(conn, account_ids)

    counts = _empty_delete_counts()
    counts.update(
        {
            "accounts": len(targets),
            "trades": fetch_row_count(conn, "trades", "account_id", account_ids),
            "equity_snapshots": count_equity_snapshots_for_account_ids(conn, account_ids),
            "backtest_runs": len(run_ids),
            "walk_forward_groups": len(walk_forward_group_ids),
            "promotion_reviews": len(review_ids),
        }
    )

    if run_ids:
        counts["backtest_trades"] = fetch_row_count(conn, "backtest_trades", "run_id", run_ids)
        counts["backtest_equity_snapshots"] = fetch_row_count(
            conn,
            "backtest_equity_snapshots",
            "run_id",
            run_ids,
        )
    if walk_forward_group_ids:
        counts["walk_forward_group_runs"] = fetch_row_count(
            conn,
            "walk_forward_group_runs",
            "group_id",
            walk_forward_group_ids,
        )
    if review_ids:
        counts["promotion_review_events"] = fetch_row_count(
            conn,
            "promotion_review_events",
            "review_id",
            review_ids,
        )

    if dry_run:
        return counts

    conn.execute("BEGIN")
    if walk_forward_group_ids:
        delete_walk_forward_group_runs_by_group_ids(conn, walk_forward_group_ids)
    if run_ids:
        delete_backtest_equity_snapshots_by_run_ids(conn, run_ids)
        delete_backtest_trades_by_run_ids(conn, run_ids)
        delete_backtest_runs_by_account_ids(conn, account_ids)
    if review_ids:
        delete_promotion_review_events_by_review_ids(conn, review_ids)
        delete_promotion_reviews_by_account_ids(conn, account_ids)
    if walk_forward_group_ids:
        delete_walk_forward_groups_by_account_ids(conn, account_ids)

    delete_equity_snapshots_by_account_ids(conn, account_ids)
    delete_trades_by_account_ids(conn, account_ids)
    delete_accounts_by_ids(conn, account_ids)
    conn.commit()

    return counts
