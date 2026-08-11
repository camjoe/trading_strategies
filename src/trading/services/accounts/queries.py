from __future__ import annotations

import sqlite3

from trading.domain.exceptions import ValidationError
from trading.models import AccountRecord, EquitySnapshotRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.snapshots import EquitySnapshotRepository


def normalize_account_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValidationError("account_name cannot be empty.")
    return normalized


def _require_positive_account_id(account_id: int) -> None:
    if account_id <= 0:
        raise ValidationError("account_id must be positive.")


def find_account(conn: sqlite3.Connection, name: str) -> AccountRecord | None:
    return AccountRepository(conn).fetch_by_name(normalize_account_name(name))


def list_account_records(conn: sqlite3.Connection) -> list[AccountRecord]:
    return AccountRepository(conn).fetch_all()


def list_account_names(conn: sqlite3.Connection) -> list[str]:
    return [account.name for account in AccountRepository(conn).fetch_all()]


def get_latest_account_snapshot(
    conn: sqlite3.Connection,
    account_id: int,
) -> EquitySnapshotRecord | None:
    _require_positive_account_id(account_id)
    return EquitySnapshotRepository(conn).fetch_latest(account_id=account_id)


def list_account_snapshots(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    limit: int,
) -> list[EquitySnapshotRecord]:
    _require_positive_account_id(account_id)
    if limit <= 0:
        raise ValidationError("limit must be positive.")
    return EquitySnapshotRepository(conn).fetch_history(account_id=account_id, limit=limit)
