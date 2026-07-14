from __future__ import annotations

import sqlite3

from trading.services.accounts import (
    AccountAlreadyExistsError,
    create_account,
    delete_account,
    preview_account_deletion,
)
from trading.services.profiles import apply_book_rotation_settings

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
    if command.rotation_settings:
        apply_book_rotation_settings(conn, command.name, {"rotation": command.rotation_settings})


def build_account_deletion_preview(account_name: str) -> dict[str, object]:
    """Shape a compact deletion preview for the admin UI."""
    with db_conn() as conn:
        preview = preview_account_deletion(conn, account_name)
    return {
        "accountName": preview.account_name,
        "descriptiveName": preview.descriptive_name,
        "strategy": preview.strategy,
    }


def delete_managed_account(account_name: str) -> str:
    """Delete one account and return its canonical name."""
    with db_conn() as conn:
        return delete_account(conn, account_name).name
