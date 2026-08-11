"""Auto-trading service package.

This package is the stable public surface for runtime auto-trading
orchestration and input preparation.
"""

from __future__ import annotations

from trading.services.auto_trading.inputs import (
    resolve_account_names,
    resolve_market_inputs,
    resolve_run_universe,
    run_accounts,
    validate_trade_count_range,
)
from trading.services.auto_trading.market import build_iv_rank_proxy
from trading.services.auto_trading.runtime import (
    is_runtime_submission_window_open,
    run_for_account,
)

__all__ = [
    "build_iv_rank_proxy",
    "is_runtime_submission_window_open",
    "resolve_account_names",
    "resolve_market_inputs",
    "resolve_run_universe",
    "run_accounts",
    "run_for_account",
    "validate_trade_count_range",
]
