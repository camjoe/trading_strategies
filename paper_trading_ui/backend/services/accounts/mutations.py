from __future__ import annotations

import sqlite3

from trading.models.account_config import AccountConfig
from trading.services.accounts_service import update_account_fields_by_id
from trading.services.profiles_service import apply_rotation_fields

from ...account_contract import AccountParamsUpdateCommand


def update_account_params(
    conn: sqlite3.Connection,
    account_id: int,
    account_name: str,
    command: AccountParamsUpdateCommand,
) -> None:
    """Update mutable account parameters. Only supplied fields are changed."""
    if command.strategy is not None:
        update_account_fields_by_id(conn, account_id, updates=["strategy = ?"], params=[command.strategy])

    if AccountConfig.has_any_field(command.config_values):
        from trading.services.accounts_service import configure_account

        configure_account(conn, account_name, command.config)

    if command.rotation_profile:
        apply_rotation_fields(conn, account_name, command.rotation_profile)
