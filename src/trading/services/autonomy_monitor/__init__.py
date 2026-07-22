"""Autonomy monitoring service.

Public surface for querying managed (``account_kind == "managed"``) account
status, books, governance, burn-in progress, and risk summary. Used by the
paper_trading_web autonomy dashboard and operators.

Concrete logic lives in focused modules beneath this package root.
"""

from __future__ import annotations

from trading.services.autonomy_monitor.queries import (
    fetch_autonomy_accounts_list,
    fetch_autonomy_account_detail,
)
from trading.services.autonomy_monitor.artifacts import (
    fetch_daily_workflow_status,
    fetch_governance_checks_status,
    fetch_burn_in_status,
)

__all__ = [
    "fetch_autonomy_accounts_list",
    "fetch_autonomy_account_detail",
    "fetch_daily_workflow_status",
    "fetch_governance_checks_status",
    "fetch_burn_in_status",
]
