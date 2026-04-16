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
    set_benchmark,
    update_account_fields_by_id,
)

__all__ = [
    "GOAL_NOT_SET_TEXT",
    "HEURISTIC_EXPLORATION_LABEL",
    "build_account_listing_lines",
    "configure_account",
    "create_account",
    "create_managed_account",
    "format_account_policy_text",
    "format_goal_text",
    "get_account",
    "list_accounts",
    "set_benchmark",
    "update_account_fields_by_id",
]
