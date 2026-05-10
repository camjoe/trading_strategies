"""IBKR paper account monitoring service.

Public surface for querying IBKR paper account status, sleeves, governance,
burn-in progress, and risk summary. Used by paper_trading_ui dashboard and
operators.

Concrete logic lives in focused modules beneath this package root.
"""

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
