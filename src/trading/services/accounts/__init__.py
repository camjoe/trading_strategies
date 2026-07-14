"""Accounts service package.

This package owns the implementation split for account listing, config, and
mutation helpers. Prefer ``trading.services.accounts`` as the stable public
import surface unless a tightly scoped internal import is clearer.
"""

from __future__ import annotations

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
    create_managed_account,
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
from trading.domain.exceptions import AccountAlreadyExistsError
from trading.domain.auto_trading_policy import (
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
)
from trading.services.accounts.config import (
    ACCOUNT_KINDS,
    ACCOUNT_KIND_LOCAL,
    ACCOUNT_KIND_MANAGED,
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
)

__all__ = [
    "ACCOUNT_KINDS",
    "ACCOUNT_KIND_LOCAL",
    "ACCOUNT_KIND_MANAGED",
    "AccountAlreadyExistsError",
    "DEFAULT_MAX_POSITION_PCT",
    "DEFAULT_TRADE_SIZE_PCT",
    "find_account",
    "GOAL_NOT_SET_TEXT",
    "HEURISTIC_EXPLORATION_LABEL",
    "INSTRUMENT_MODES",
    "OPTION_TYPES",
    "build_account_listing_lines",
    "configure_account",
    "create_account",
    "create_managed_account",
    "format_account_policy_text",
    "format_goal_text",
    "get_account",
    "get_latest_account_snapshot",
    "list_accounts",
    "list_account_names",
    "list_account_records",
    "list_account_snapshots",
    "load_runtime_eligible_account_names",
    "RISK_POLICIES",
    "set_account_strategy",
    "set_benchmark",
]
