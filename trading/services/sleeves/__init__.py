"""Sleeve services package.

This package is the stable public sleeve-orchestration surface for sleeve-level
accounting updates and account-vs-sleeve reconciliation.
"""

from trading.services.sleeves.accounting import SleeveFillApplicationResult, apply_sleeve_fill
from trading.services.sleeves.execution import (
    SleeveTradeIntent,
    generate_sleeve_trade_intents,
    run_sleeve_mode_for_account,
)
from trading.services.sleeves.reconciliation import (
    SleeveEquityReconciliationResult,
    reconcile_sleeves_vs_account_equity,
    reconcile_sleeves_vs_latest_snapshot,
)

__all__ = [
    "SleeveFillApplicationResult",
    "SleeveTradeIntent",
    "SleeveEquityReconciliationResult",
    "apply_sleeve_fill",
    "generate_sleeve_trade_intents",
    "reconcile_sleeves_vs_account_equity",
    "reconcile_sleeves_vs_latest_snapshot",
    "run_sleeve_mode_for_account",
]
