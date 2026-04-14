from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from trading.services.admin_service import build_managed_account_delete_counts, delete_accounts
from trading.services.profiles_service import apply_rotation_fields

from .db import db_conn


def apply_account_rotation_profile(
    conn: sqlite3.Connection,
    account_name: str,
    rotation_profile: dict[str, object],
) -> None:
    apply_rotation_fields(conn, account_name, rotation_profile)


def delete_account_and_dependents(account_name: str) -> dict[str, int]:
    try:
        with db_conn() as conn:
            deleted = delete_accounts(
                conn,
                account_names=[account_name],
                delete_all=False,
                dry_run=False,
            )
    except ValueError as error:
        if "Accounts not found:" in str(error):
            raise HTTPException(status_code=404, detail=f"Account '{account_name}' not found.") from error
        raise

    return build_managed_account_delete_counts(deleted)
