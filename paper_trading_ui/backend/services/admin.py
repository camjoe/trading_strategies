from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from trading.models import RotationConfig
from trading.services.accounts_service import update_account_fields_by_id
from trading.services.admin_service import delete_accounts

from .db import get_account_row


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def update_account_rotation_settings(
    conn: sqlite3.Connection,
    account_name: str,
    rotation: RotationConfig,
) -> None:
    account = get_account_row(conn, account_name)
    db_values = rotation.to_db_dict()
    updates = [f"{key} = ?" for key in db_values]
    params = list(db_values.values())
    update_account_fields_by_id(
        conn,
        account_id=int(account["id"]),
        updates=updates,
        params=params,
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
