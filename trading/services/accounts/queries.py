from __future__ import annotations

from collections.abc import Collection
import sqlite3

from trading.models import AccountRecord
from trading.repositories.accounts_repository import (
    fetch_account_by_name,
    fetch_account_rows,
    fetch_all_account_names,
    _load_all_account_names,
)
from trading.repositories.snapshots_repository import (
    fetch_latest_snapshot_row,
    fetch_snapshot_history_rows,
)
from trading.services.accounts.config import normalize_account_kind


def _normalize_account_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("account_name cannot be empty.")
    return normalized


def _normalize_account_kinds(account_kinds: Collection[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for kind in account_kinds:
        resolved = normalize_account_kind(str(kind))
        if resolved not in normalized:
            normalized.append(resolved)
    return tuple(normalized)


def _require_positive_account_id(account_id: int) -> None:
    if account_id <= 0:
        raise ValueError("account_id must be positive.")


def find_account(conn: sqlite3.Connection, name: str) -> AccountRecord | None:
    return fetch_account_by_name(conn, _normalize_account_name(name))


def list_account_records(
    conn: sqlite3.Connection,
    *,
    account_kinds: Collection[str] | None = None,
) -> list[AccountRecord]:
    if account_kinds is None:
        return fetch_account_rows(conn)

    normalized_kinds = _normalize_account_kinds(account_kinds)
    if not normalized_kinds:
        return []
    return fetch_account_rows(conn, account_kinds=normalized_kinds)


def list_account_names(
    conn: sqlite3.Connection,
    *,
    account_kinds: Collection[str] | None = None,
) -> list[str]:
    if account_kinds is None:
        return fetch_all_account_names(conn)
    return [row.name for row in list_account_records(conn, account_kinds=account_kinds)]


def get_latest_account_snapshot(
    conn: sqlite3.Connection,
    account_id: int,
) -> dict[str, object] | None:
    _require_positive_account_id(account_id)
    return fetch_latest_snapshot_row(conn, account_id=account_id)


def list_account_snapshots(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    limit: int,
) -> list[dict[str, object]]:
    _require_positive_account_id(account_id)
    if limit <= 0:
        raise ValueError("limit must be positive.")
    return fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def load_all_account_names() -> list[str]:
    return _load_all_account_names()
