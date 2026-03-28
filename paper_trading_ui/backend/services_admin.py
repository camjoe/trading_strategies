from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def build_rotation_schedule_json(value: list[str] | None) -> str | None:
    if not value:
        return None
    normalized = [item.strip() for item in value if item and item.strip()]
    if not normalized:
        return None
    unique: list[str] = []
    for item in normalized:
        if item not in unique:
            unique.append(item)
    return json.dumps(unique, separators=(",", ":"))


def delete_account_and_dependents(conn: sqlite3.Connection, account_name: str) -> dict[str, int]:
    account = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.")

    account_id = int(account["id"])
    run_rows = conn.execute("SELECT id FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchall()
    run_ids = tuple(int(row["id"]) for row in run_rows)

    counts = {
        "accounts": 1,
        "trades": int(conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = ?", (account_id,)).fetchone()["n"]),
        "equitySnapshots": int(
            conn.execute("SELECT COUNT(*) AS n FROM equity_snapshots WHERE account_id = ?", (account_id,)).fetchone()["n"]
        ),
        "backtestRuns": len(run_ids),
        "backtestTrades": 0,
        "backtestEquitySnapshots": 0,
    }

    conn.execute("BEGIN")
    if run_ids:
        placeholders = ",".join(["?"] * len(run_ids))
        counts["backtestTrades"] = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM backtest_trades WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchone()["n"]
        )
        counts["backtestEquitySnapshots"] = int(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchone()["n"]
        )
        conn.execute(f"DELETE FROM backtest_equity_snapshots WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM backtest_trades WHERE run_id IN ({placeholders})", run_ids)
        conn.execute(f"DELETE FROM backtest_runs WHERE id IN ({placeholders})", run_ids)

    conn.execute("DELETE FROM equity_snapshots WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM trades WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    return counts
