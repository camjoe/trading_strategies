from __future__ import annotations

import sqlite3

from trading.utils.coercion import coerce_int, row_expect_int
from trading.repositories.admin_repository import (
    count_rows,
    delete_accounts_by_ids,
    delete_backtest_equity_snapshots_by_run_ids,
    delete_backtest_runs_by_account_ids,
    delete_backtest_trades_by_run_ids,
    delete_equity_snapshots_by_account_ids,
    delete_trades_by_account_ids,
    fetch_accounts_by_names,
    fetch_all_accounts,
    fetch_backtest_run_rows_for_accounts,
)


def _resolve_delete_targets(conn: sqlite3.Connection, names: list[str], delete_all: bool) -> list[dict[str, object]]:
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


def delete_accounts(
    conn: sqlite3.Connection,
    *,
    account_names: list[str],
    delete_all: bool,
    dry_run: bool,
) -> dict[str, int]:
    targets = _resolve_delete_targets(conn, account_names, delete_all)
    if not targets:
        return {
            "accounts": 0,
            "trades": 0,
            "equity_snapshots": 0,
            "backtest_runs": 0,
            "backtest_trades": 0,
            "backtest_equity_snapshots": 0,
        }

    account_ids_list: list[int] = []
    for item in targets:
        account_id = coerce_int(item["id"])
        if account_id is None:
            continue
        account_ids_list.append(account_id)
    account_ids: tuple[int, ...] = tuple(account_ids_list)
    if len(account_ids) != len(targets):
        raise ValueError("Unexpected non-integer account id in delete target set.")

    run_rows = fetch_backtest_run_rows_for_accounts(conn, account_ids)
    run_ids_list: list[int] = []
    for row in run_rows:
        run_id = coerce_int(row["id"])
        if run_id is None:
            continue
        run_ids_list.append(run_id)
    run_ids: tuple[int, ...] = tuple(run_ids_list)
    if len(run_ids) != len(run_rows):
        raise ValueError("Unexpected non-integer backtest run id in delete target set.")

    account_placeholders_where = f"account_id IN ({','.join(['?'] * len(account_ids))})"
    counts: dict[str, int] = {
        "accounts": len(targets),
        "trades": count_rows(conn, "trades", account_placeholders_where, account_ids),
        "equity_snapshots": count_rows(conn, "equity_snapshots", account_placeholders_where, account_ids),
        "backtest_runs": len(run_ids),
        "backtest_trades": 0,
        "backtest_equity_snapshots": 0,
    }

    if run_ids:
        run_placeholders_where = f"run_id IN ({','.join(['?'] * len(run_ids))})"
        counts["backtest_trades"] = count_rows(conn, "backtest_trades", run_placeholders_where, run_ids)
        counts["backtest_equity_snapshots"] = count_rows(conn, "backtest_equity_snapshots", run_placeholders_where, run_ids)

    if dry_run:
        return counts

    conn.execute("BEGIN")
    if run_ids:
        delete_backtest_equity_snapshots_by_run_ids(conn, run_ids)
        delete_backtest_trades_by_run_ids(conn, run_ids)
        delete_backtest_runs_by_account_ids(conn, account_ids)

    delete_equity_snapshots_by_account_ids(conn, account_ids)
    delete_trades_by_account_ids(conn, account_ids)
    delete_accounts_by_ids(conn, account_ids)
    conn.commit()

    return counts
