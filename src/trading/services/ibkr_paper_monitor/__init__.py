"""IBKR paper account monitoring service.

Public surface for querying IBKR paper account status, books, governance,
burn-in progress, and risk summary. Used by paper_trading_web dashboard and
operators.

Concrete logic lives in focused modules beneath this package root.
"""

from __future__ import annotations

from trading.services.ibkr_paper_monitor.queries import (
    fetch_ibkr_paper_accounts_list,
    fetch_ibkr_paper_account_detail,
)
from trading.services.ibkr_paper_monitor.artifacts import (
    fetch_daily_workflow_status,
    fetch_governance_checks_status,
    fetch_burn_in_status,
)

__all__ = [
    "fetch_ibkr_paper_accounts_list",
    "fetch_ibkr_paper_account_detail",
    "fetch_daily_workflow_status",
    "fetch_governance_checks_status",
    "fetch_burn_in_status",
]
