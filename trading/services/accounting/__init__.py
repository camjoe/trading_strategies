"""Accounting service package.

This package owns the accounting service split for persisted trade queries and
trade-recording workflows. Prefer ``trading.services.accounting`` as the stable
public import surface unless a tightly scoped internal import is clearer.
"""

from trading.services.accounting.mutations import record_trade
from trading.services.accounting.queries import list_account_trades, load_account_state

__all__ = [
    "list_account_trades",
    "load_account_state",
    "record_trade",
]
