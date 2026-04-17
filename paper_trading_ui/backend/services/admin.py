from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from trading.services.accounts_service import (
    AccountAlreadyExistsError,
    create_account,
)
from trading.services.profiles_service import apply_rotation_fields
from trading.services.admin_service import build_managed_account_delete_counts, delete_accounts

from ..account_contract import AdminCreateAccountCommand
from .db import db_conn


def create_account_with_rotation(conn: sqlite3.Connection, command: AdminCreateAccountCommand) -> None:
    """Create account and apply rotation profile, translating domain errors to ValueError."""
    try:
        create_account(
            conn,
            name=command.name,
            strategy=command.strategy,
            initial_cash=command.initial_cash,
            benchmark_ticker=command.benchmark_ticker,
            config=command.config,
        )
    except (ValueError, AccountAlreadyExistsError) as error:
        raise ValueError(str(error)) from error
    apply_rotation_fields(conn, command.name, command.rotation_profile)


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
