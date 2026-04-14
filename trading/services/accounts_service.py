from __future__ import annotations

import sqlite3

from trading.repositories.accounts_repository import (
    fetch_account_by_name as _repo_fetch_account_by_name,
    fetch_account_rows_excluding_name,
    fetch_all_account_names as _repo_fetch_all_account_names,
    fetch_all_account_names_from_conn,
)
from trading.repositories.snapshots_repository import (
    fetch_latest_snapshot_row as _repo_fetch_latest_snapshot_row,
    fetch_snapshot_history_rows as _repo_fetch_snapshot_history_rows,
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
    create_managed_account,
    get_account,
    set_benchmark,
    update_account_fields_by_id,
)


def fetch_account_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return _repo_fetch_account_by_name(conn, name)


def fetch_all_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names_from_conn(conn)


def fetch_account_rows_excluding(conn: sqlite3.Connection, *, excluded_name: str) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding_name(conn, excluded_name=excluded_name)


def fetch_latest_snapshot_row(conn: sqlite3.Connection, account_id: int) -> sqlite3.Row | None:
    return _repo_fetch_latest_snapshot_row(conn, account_id=account_id)


def fetch_snapshot_history_rows(conn: sqlite3.Connection, account_id: int, *, limit: int) -> list[sqlite3.Row]:
    return _repo_fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def load_all_account_names() -> list[str]:
    return _repo_fetch_all_account_names()
