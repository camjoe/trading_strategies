"""Runtime account loader — opens its own DB connection to fetch eligible accounts.

This module is the sole deliberate exception to the rule that ``trading/services``
must not import from ``trading.database`` directly.  It is kept isolated here so
that the exception is explicit and the scope is narrow: this file's only job is to
bridge the service layer to the backend connection factory for runtime job runners
that need a fresh list of accounts without an injected connection.
"""

from __future__ import annotations

from src.infrastructure.database.db_backend import get_backend
from trading.repositories.accounts import AccountRepository


def load_runtime_eligible_account_names() -> list[str]:
    conn = get_backend().open_connection()
    try:
        return AccountRepository(conn).fetch_names()
    finally:
        conn.close()
