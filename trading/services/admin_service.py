from __future__ import annotations

from collections.abc import Sequence
import sqlite3

from trading.utils.coercion import coerce_int, row_expect_int
from trading.repositories.admin_repository import (
    count_rows,
    delete_accounts_by_ids,
    delete_backtest_equity_snapshots_by_run_ids,
    delete_backtest_runs_by_account_ids,
    delete_backtest_trades_by_run_ids,
    delete_equity_snapshots_by_account_ids,
    delete_promotion_review_events_by_review_ids,
    delete_promotion_reviews_by_account_ids,
    delete_trades_by_account_ids,
    fetch_accounts_by_names,
    fetch_all_accounts,
    fetch_backtest_run_rows_for_accounts,
    fetch_promotion_review_rows_for_accounts,
)

DELETE_COUNT_KEYS = (
    "accounts",
    "trades",
    "equity_snapshots",
    "backtest_runs",
    "backtest_trades",
    "backtest_equity_snapshots",
    "promotion_reviews",
    "promotion_review_events",
)


def _resolve_delete_targets(
    conn: sqlite3.Connection,
    names: list[str],
    delete_all: bool,
) -> list[dict[str, object]]:
    if delete_all:
        rows = fetch_all_accounts(conn)
    else:
        rows = fetch_accounts_by_names(conn, tuple(names))
        found = {str(row["name"]) for row in rows}
        missing = [name for name in names if name not in found]
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(f"Accounts not found: {missing_text}")

    normalized: list[dict[str, object]] = []
    for row in rows:
        account_id = row_expect_int(row, "id")
        normalized.append({"id": account_id, "name": str(row["name"])})
    return normalized


def _empty_delete_counts() -> dict[str, int]:
    return {key: 0 for key in DELETE_COUNT_KEYS}


def _collect_required_ids(
    rows: Sequence[sqlite3.Row | dict[str, object]],
    *,
    key: str,
    label: str,
) -> tuple[int, ...]:
    ids = tuple(
        account_id
        for row in rows
        if (account_id := coerce_int(row[key])) is not None
    )
    if len(ids) != len(rows):
        raise ValueError(f"Unexpected non-integer {label} id in delete target set.")
    return ids


def _in_clause(column_name: str, values: tuple[int, ...]) -> str:
    return f"{column_name} IN ({','.join(['?'] * len(values))})"


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

    run_rows = fetch_backtest_run_rows_for_accounts(conn, account_ids)
    run_ids = _collect_required_ids(run_rows, key="id", label="backtest run")

    review_rows = fetch_promotion_review_rows_for_accounts(conn, account_ids)
    review_ids = _collect_required_ids(review_rows, key="id", label="promotion review")

    account_placeholders_where = _in_clause("account_id", account_ids)
    counts = _empty_delete_counts()
    counts.update(
        {
            "accounts": len(targets),
            "trades": count_rows(conn, "trades", account_placeholders_where, account_ids),
            "equity_snapshots": count_rows(conn, "equity_snapshots", account_placeholders_where, account_ids),
            "backtest_runs": len(run_ids),
            "promotion_reviews": len(review_ids),
        }
    )

    if run_ids:
        run_placeholders_where = _in_clause("run_id", run_ids)
        counts["backtest_trades"] = count_rows(conn, "backtest_trades", run_placeholders_where, run_ids)
        counts["backtest_equity_snapshots"] = count_rows(
            conn,
            "backtest_equity_snapshots",
            run_placeholders_where,
            run_ids,
        )
    if review_ids:
        review_placeholders_where = _in_clause("review_id", review_ids)
        counts["promotion_review_events"] = count_rows(
            conn,
            "promotion_review_events",
            review_placeholders_where,
            review_ids,
        )

    if dry_run:
        return counts

    conn.execute("BEGIN")
    if run_ids:
        delete_backtest_equity_snapshots_by_run_ids(conn, run_ids)
        delete_backtest_trades_by_run_ids(conn, run_ids)
        delete_backtest_runs_by_account_ids(conn, account_ids)
    if review_ids:
        delete_promotion_review_events_by_review_ids(conn, review_ids)
        delete_promotion_reviews_by_account_ids(conn, account_ids)

    delete_equity_snapshots_by_account_ids(conn, account_ids)
    delete_trades_by_account_ids(conn, account_ids)
    delete_accounts_by_ids(conn, account_ids)
    conn.commit()

    return counts
