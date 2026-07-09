"""Auto-trading service package.

This package is the stable public surface for runtime auto-trading
orchestration, input preparation, and rotation bridge helpers.
"""

from __future__ import annotations

from trading.services.auto_trading.inputs import (
    EXECUTION_MODE_ACCOUNT,
    EXECUTION_MODE_BOOK,
    resolve_account_names,
    resolve_market_inputs,
    run_accounts,
    validate_execution_mode,
    validate_trade_count_range,
)
from trading.services.auto_trading.market import build_iv_rank_proxy
from trading.services.auto_trading.rotation_bridge import (
    RotationDeps,
    rotate_runtime_account_if_due,
    select_account_rotation_strategy,
)
from trading.services.auto_trading.runtime import (
    reconcile_open_broker_orders,
    reconcile_open_ib_orders,
    run_for_account,
)

__all__ = [
    "RotationDeps",
    "EXECUTION_MODE_ACCOUNT",
    "EXECUTION_MODE_BOOK",
    "build_iv_rank_proxy",
    "reconcile_open_broker_orders",
    "reconcile_open_ib_orders",
    "resolve_account_names",
    "resolve_market_inputs",
    "rotate_runtime_account_if_due",
    "run_accounts",
    "run_for_account",
    "select_account_rotation_strategy",
    "validate_execution_mode",
    "validate_trade_count_range",
]
