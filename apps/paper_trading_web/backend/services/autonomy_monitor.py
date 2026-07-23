"""UI layer service for the autonomy monitoring dashboard.

This layer handles:
- Delegating all data fetching to trading.services.autonomy_monitor (both DB and artifacts)
- Combining responses into unified dashboard response

All data access (DB queries and artifact reading) is delegated to trading layer.
This module only handles response aggregation.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from trading.services.autonomy_monitor import (
    fetch_autonomy_account_detail as fetch_db_data,
    fetch_autonomy_accounts_list as fetch_db_accounts_list,
    fetch_burn_in_status,
    fetch_daily_workflow_status,
    fetch_governance_checks_status,
)


def fetch_autonomy_accounts_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch list of managed accounts with book summary.

    Delegates to trading.services.autonomy_monitor for DB queries.
    """
    return fetch_db_accounts_list(conn)


def fetch_autonomy_account_data(
    conn: sqlite3.Connection,
    account_name: str,
) -> dict[str, Any]:
    """Fetch comprehensive autonomy dashboard data for a managed account.

    Combines:
    - DB data from trading.services.autonomy_monitor (account, books, rotations, risk)
    - Artifact data from trading.services.autonomy_monitor (workflow, governance, burn-in)

    Raises ValueError if account not found.
    """
    # Fetch DB data from trading service layer
    account_data = fetch_db_data(conn, account_name)

    # Fetch artifact data from trading service layer
    account_data["daily_workflow"] = fetch_daily_workflow_status()
    account_data["governance_checks"] = fetch_governance_checks_status()
    account_data["burn_in_status"] = fetch_burn_in_status()

    return account_data
