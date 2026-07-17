from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccountDeletionPreview:
    """Compact impact summary shown before an account is deleted."""

    account_name: str
    descriptive_name: str
    strategy: str
