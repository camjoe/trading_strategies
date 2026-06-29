from __future__ import annotations

import sqlite3

from trading.services.accounts import (
    AccountAlreadyExistsError,
    create_account,
)
from trading.services.admin import delete_accounts
from trading.services.profiles import apply_rotation_fields

from ..account_contract import AdminCreateAccountCommand
from .db import db_conn

_MANAGED_ACCOUNT_DELETE_COUNT_KEYS = {
    "accounts": "accounts",
    "trades": "trades",
    "equity_snapshots": "equitySnapshots",
    "backtest_runs": "backtestRuns",
    "backtest_trades": "backtestTrades",
    "backtest_equity_snapshots": "backtestEquitySnapshots",
}


def _build_managed_account_delete_counts(counts: dict[str, int]) -> dict[str, int]:
    return {
        ui_key: int(counts.get(service_key, 0)) for service_key, ui_key in _MANAGED_ACCOUNT_DELETE_COUNT_KEYS.items()
    }


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
    # delete_accounts raises NotFoundError for unknown accounts, mapped to HTTP 404
    # by the app-level exception handler (see docs/adr/007-ui-error-mapping.md).
    with db_conn() as conn:
        deleted = delete_accounts(
            conn,
            account_names=[account_name],
            delete_all=False,
            dry_run=False,
        )
    return _build_managed_account_delete_counts(deleted)
