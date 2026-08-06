"""Runtime account loader — opens its own DB connection to fetch eligible accounts.

This module is the sole deliberate exception to the rule that ``trading/services``
must not import from ``infrastructure.database`` directly.  It is kept isolated here
so that the exception is explicit and the scope is narrow: this file's only job is to
bridge the service layer to the shared connection helper for runtime job runners
that need a fresh list of accounts without an injected connection.

It goes through ``db_session()`` rather than the backend directly, so the
schema-revision gate applies here as it does to every other application query.
"""

from __future__ import annotations

from infrastructure.database.connection import db_session
from trading.repositories.accounts import AccountRepository


def load_runtime_eligible_account_names() -> list[str]:
    with db_session() as conn:
        return AccountRepository(conn).fetch_names()
