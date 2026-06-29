"""Admin service package.

This package is the stable public admin surface for operator-facing account
deletion flows.
"""

from __future__ import annotations

from trading.services.admin.deletions import (
    DELETE_COUNT_KEYS,
    delete_accounts,
    iter_delete_count_items,
)

__all__ = [
    "DELETE_COUNT_KEYS",
    "delete_accounts",
    "iter_delete_count_items",
]
