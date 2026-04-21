"""Internal accounts service package.

This package owns the implementation split for account listing, config, and
mutation helpers. Prefer ``trading.services.accounts_service`` as the stable
public import surface unless a tightly scoped internal import is clearer.
"""

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
    load_all_account_names,
)

__all__ = [
    "find_account",
    "GOAL_NOT_SET_TEXT",
    "HEURISTIC_EXPLORATION_LABEL",
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
    "load_all_account_names",
    "set_account_strategy",
    "set_benchmark",
]
