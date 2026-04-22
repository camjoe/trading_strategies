"""Admin service package.

This package is the stable public admin surface for operator-facing account
deletion flows.
"""

from trading.services.admin.deletions import (
    DELETE_COUNT_FIELDS,
    DELETE_COUNT_KEYS,
    DeleteCountField,
    build_managed_account_delete_counts,
    delete_accounts,
    iter_delete_count_items,
)

__all__ = [
    "DELETE_COUNT_FIELDS",
    "DELETE_COUNT_KEYS",
    "DeleteCountField",
    "build_managed_account_delete_counts",
    "delete_accounts",
    "iter_delete_count_items",
]
