"""Runtime account loader — opens its own DB connection to list every account name.

The only ``trading/services`` module allowed to import ``infrastructure.database``
(`layer_check` carries a file-level exception for it). Keep it to this one job so
the exception stays narrow; every other service takes an injected connection.
"""

from __future__ import annotations

from infrastructure.database.connection import db_session
from trading.services.accounts.queries import list_account_names


def load_account_names() -> list[str]:
    with db_session() as conn:
        return list_account_names(conn)
