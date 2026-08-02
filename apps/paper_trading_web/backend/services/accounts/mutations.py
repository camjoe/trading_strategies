from __future__ import annotations

import sqlite3

from trading.models.accounts import AccountConfig
from trading.services.accounts import set_account_strategy
from trading.services.profiles import apply_book_rotation_settings

from ...account_contract import AccountParamsUpdateCommand


def update_account_params(
    conn: sqlite3.Connection,
    account_name: str,
    command: AccountParamsUpdateCommand,
) -> None:
    """Update mutable account parameters. Only supplied fields are changed."""
    if command.strategy is not None:
        set_account_strategy(conn, account_name, command.strategy)

    if AccountConfig.has_any_field(command.config_values):
        from trading.services.accounts import configure_account

        configure_account(conn, account_name, command.config)

    if command.rotation_settings:
        apply_book_rotation_settings(conn, account_name, {"rotation": command.rotation_settings})
