"""Runtime account loader — opens its own DB connection to fetch eligible accounts.

The only ``trading/services`` module allowed to import ``infrastructure.database``
(`layer_check` carries a file-level exception for it). Keep it to this one job so
the exception stays narrow; every other service takes an injected connection.
"""

from __future__ import annotations

from infrastructure.database.connection import db_session
from trading.repositories.accounts import AccountRepository


def load_runtime_eligible_account_names() -> list[str]:
    with db_session() as conn:
        return AccountRepository(conn).fetch_names()
