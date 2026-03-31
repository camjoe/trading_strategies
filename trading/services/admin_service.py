from __future__ import annotations

from trading.coercion import coerce_int, row_expect_int
from trading.database.db import ensure_db


def _resolve_delete_targets(conn, names: list[str], delete_all: bool) -> list[dict[str, object]]:
    if delete_all:
        rows = conn.execute("SELECT id, name FROM accounts ORDER BY name ASC").fetchall()
    else:
        placeholders = ",".join(["?"] * len(names))
        rows = conn.execute(
            f"SELECT id, name FROM accounts WHERE name IN ({placeholders}) ORDER BY name ASC",
            tuple(names),
        ).fetchall()

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


def _count_rows(conn, table: str, where_sql: str, params: tuple[object, ...]) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where_sql}", params).fetchone()
    if row is None:
        return 0
    count = coerce_int(row["n"])
    if count is None:
        raise ValueError(f"Unexpected non-integer count from table '{table}'.")
    return count


def delete_accounts(
    *,
    account_names: list[str],
    delete_all: bool,
    dry_run: bool,
) -> dict[str, int]:
    conn = ensure_db()
    try:
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
        account_placeholders = ",".join(["?"] * len(account_ids))

        run_rows = conn.execute(
            f"SELECT id FROM backtest_runs WHERE account_id IN ({account_placeholders})",
            account_ids,
        ).fetchall()
        run_ids_list: list[int] = []
        for row in run_rows:
            run_id = coerce_int(row["id"])
            if run_id is None:
                continue
            run_ids_list.append(run_id)
        run_ids: tuple[int, ...] = tuple(run_ids_list)
        if len(run_ids) != len(run_rows):
            raise ValueError("Unexpected non-integer backtest run id in delete target set.")

        counts = {
            "accounts": len(targets),
            "trades": _count_rows(conn, "trades", f"account_id IN ({account_placeholders})", account_ids),
            "equity_snapshots": _count_rows(
                conn,
                "equity_snapshots",
                f"account_id IN ({account_placeholders})",
                account_ids,
            ),
            "backtest_runs": len(run_ids),
            "backtest_trades": 0,
            "backtest_equity_snapshots": 0,
        }

        if run_ids:
            run_placeholders = ",".join(["?"] * len(run_ids))
            counts["backtest_trades"] = _count_rows(
                conn,
                "backtest_trades",
                f"run_id IN ({run_placeholders})",
                run_ids,
            )
            counts["backtest_equity_snapshots"] = _count_rows(
                conn,
                "backtest_equity_snapshots",
                f"run_id IN ({run_placeholders})",
                run_ids,
            )

        if dry_run:
            return counts

        conn.execute("BEGIN")
        if run_ids:
            run_placeholders = ",".join(["?"] * len(run_ids))
            conn.execute(f"DELETE FROM backtest_equity_snapshots WHERE run_id IN ({run_placeholders})", run_ids)
            conn.execute(f"DELETE FROM backtest_trades WHERE run_id IN ({run_placeholders})", run_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE id IN ({run_placeholders})", run_ids)

        conn.execute(f"DELETE FROM equity_snapshots WHERE account_id IN ({account_placeholders})", account_ids)
        conn.execute(f"DELETE FROM trades WHERE account_id IN ({account_placeholders})", account_ids)
        conn.execute(f"DELETE FROM accounts WHERE id IN ({account_placeholders})", account_ids)
        conn.commit()

        return counts
    finally:
        conn.close()
