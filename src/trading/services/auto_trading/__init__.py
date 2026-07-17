"""Auto-trading service package.

This package is the stable public surface for runtime auto-trading
orchestration and input preparation.
"""

from __future__ import annotations

from trading.services.auto_trading.inputs import (
    resolve_account_names,
    resolve_market_inputs,
    run_accounts,
    validate_trade_count_range,
)
from trading.services.auto_trading.market import build_iv_rank_proxy
from trading.services.auto_trading.runtime import (
    reconcile_open_broker_orders,
    reconcile_open_ib_orders,
    run_for_account,
)

__all__ = [
    "build_iv_rank_proxy",
    "reconcile_open_broker_orders",
    "reconcile_open_ib_orders",
    "resolve_account_names",
    "resolve_market_inputs",
    "run_accounts",
    "run_for_account",
    "validate_trade_count_range",
]
