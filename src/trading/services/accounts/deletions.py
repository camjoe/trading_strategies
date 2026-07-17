from __future__ import annotations

import sqlite3

from trading.domain.exceptions import NotFoundError
from trading.models import AccountDeletionPreview, AccountRecord
from trading.repositories.accounts import AccountRepository


def _normalize_account_name(account_name: str) -> str:
    normalized = account_name.strip()
    if not normalized:
        raise ValueError("account_name cannot be empty.")
    return normalized


def preview_account_deletion(
    conn: sqlite3.Connection,
    account_name: str,
) -> AccountDeletionPreview:
    """Describe the cascade impact before one account is deleted."""
    normalized_name = _normalize_account_name(account_name)
    repo = AccountRepository(conn)
    account = repo.fetch_by_name(normalized_name)
    if account is None:
        raise NotFoundError(f"Account '{normalized_name}' not found.")
    # accounts.strategy was dropped in revision 0008; the preview shows the
    # assignment-derived active strategy.
    from trading.services.books.book_assignments import active_strategy_for_account

    return AccountDeletionPreview(
        account_name=account.name,
        descriptive_name=account.descriptive_name or account.name,
        strategy=active_strategy_for_account(conn, account.id),
    )


def delete_account(conn: sqlite3.Connection, account_name: str) -> AccountRecord:
    """Delete one account and rely on database cascades for its owned rows."""
    normalized_name = _normalize_account_name(account_name)
    deleted = AccountRepository(conn).delete_by_name(normalized_name)
    if deleted is None:
        raise NotFoundError(f"Account '{normalized_name}' not found.")
    return deleted
