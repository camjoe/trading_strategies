from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from trading.interfaces.runtime.data_ops.admin import delete_accounts
from trading.repositories.accounts_repository import update_account_fields

from .services_db import get_account_row


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


def update_account_rotation_settings(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    rotation_enabled: bool,
    rotation_mode: str,
    rotation_optimality_mode: str,
    rotation_interval_days: int,
    rotation_lookback_days: int,
    rotation_schedule: list[str] | None,
    rotation_active_index: int,
    rotation_last_at: str | None,
    rotation_active_strategy: str | None,
) -> None:
    account = get_account_row(conn, account_name)
    update_account_fields(
        conn,
        account_id=int(account["id"]),
        updates=[
            "rotation_enabled = ?",
            "rotation_mode = ?",
            "rotation_optimality_mode = ?",
            "rotation_interval_days = ?",
            "rotation_lookback_days = ?",
            "rotation_schedule = ?",
            "rotation_active_index = ?",
            "rotation_last_at = ?",
            "rotation_active_strategy = ?",
        ],
        params=[
            1 if rotation_enabled else 0,
            rotation_mode.strip().lower(),
            rotation_optimality_mode.strip().lower(),
            rotation_interval_days,
            rotation_lookback_days,
            build_rotation_schedule_json(rotation_schedule),
            int(rotation_active_index),
            clean_text(rotation_last_at),
            clean_text(rotation_active_strategy),
        ],
    )


def delete_account_and_dependents(account_name: str) -> dict[str, int]:
    try:
        deleted = delete_accounts(
            account_names=[account_name],
            delete_all=False,
            dry_run=False,
        )
    except ValueError as error:
        if "Accounts not found:" in str(error):
            raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.") from error
        raise

    return {
        "accounts": int(deleted["accounts"]),
        "trades": int(deleted["trades"]),
        "equitySnapshots": int(deleted["equity_snapshots"]),
        "backtestRuns": int(deleted["backtest_runs"]),
        "backtestTrades": int(deleted["backtest_trades"]),
        "backtestEquitySnapshots": int(deleted["backtest_equity_snapshots"]),
    }
