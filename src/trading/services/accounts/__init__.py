"""Accounts service package.

This package owns the implementation split for account listing, config,
mutation, and deletion helpers. Prefer ``trading.services.accounts`` as the stable public
import surface unless a tightly scoped internal import is clearer.
"""

from __future__ import annotations

from trading.domain.auto_trading_policy import (
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
)
from trading.domain.exceptions import AccountAlreadyExistsError
from trading.services.accounts.config import (
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
)
from trading.services.accounts.deletions import (
    delete_account,
    preview_account_deletion,
)
from trading.services.accounts.listing import (
    GOAL_NOT_SET_TEXT,
    HEURISTIC_EXPLORATION_LABEL,
    build_account_listing_lines,
    format_account_policy_text,
    format_goal_text,
    list_accounts,
)
from trading.services.accounts.mutations import (
    configure_account,
    create_account,
    get_account,
    set_account_strategy,
    set_benchmark,
)
from trading.services.accounts.queries import (
    find_account,
    get_latest_account_snapshot,
    list_account_names,
    list_account_records,
    list_account_snapshots,
)
from trading.services.accounts.runtime_loader import load_runtime_eligible_account_names

__all__ = [
    "AccountAlreadyExistsError",
    "DEFAULT_MAX_POSITION_PCT",
    "DEFAULT_TRADE_SIZE_PCT",
    "delete_account",
    "find_account",
    "GOAL_NOT_SET_TEXT",
    "HEURISTIC_EXPLORATION_LABEL",
    "INSTRUMENT_MODES",
    "OPTION_TYPES",
    "build_account_listing_lines",
    "configure_account",
    "create_account",
    "format_account_policy_text",
    "format_goal_text",
    "get_account",
    "get_latest_account_snapshot",
    "list_accounts",
    "list_account_names",
    "list_account_records",
    "list_account_snapshots",
    "load_runtime_eligible_account_names",
    "preview_account_deletion",
    "RISK_POLICIES",
    "set_account_strategy",
    "set_benchmark",
]
