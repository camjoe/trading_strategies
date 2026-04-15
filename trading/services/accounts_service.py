"""Stable public facade for account-related service helpers.

External callers should keep importing from ``trading.services.accounts_service``.
The ``trading.services.accounts.*`` package is the implementation split used to
organize listing, config, and mutation responsibilities internally.

This module also re-exports domain constants and ``AccountAlreadyExistsError`` so
that callers never need to reach into domain or config sub-packages directly:

- ``DEFAULT_MAX_POSITION_PCT``, ``DEFAULT_TRADE_SIZE_PCT`` — default position-sizing
  constants from ``trading.domain.auto_trader_policy``.
- ``parse_rotation_schedule``, ``parse_rotation_overlay_watchlist``,
  ``OPTIMALITY_MODES``, ``ROTATION_MODES``, ``ROTATION_OVERLAY_MODES`` — rotation
  config parsers and allowed-value sets from ``trading.domain.rotation``.
- ``INSTRUMENT_MODES``, ``OPTION_TYPES``, ``RISK_POLICIES`` — account config
  allowed-value sets from ``trading.services.accounts.config``.
- ``AccountAlreadyExistsError`` — domain exception raised on duplicate account
  creation, from ``trading.domain.exceptions``.
"""

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
    GOAL_NOT_SET_TEXT,  # re-exported; used by reporting_service
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

# Re-exported for callers that should not reach into domain directly.
from trading.domain.exceptions import AccountAlreadyExistsError  # noqa: F401
from trading.domain.auto_trader_policy import (  # noqa: F401
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_TRADE_SIZE_PCT,
)
from trading.domain.rotation import (  # noqa: F401
    parse_rotation_overlay_watchlist,
    parse_rotation_schedule,
    OPTIMALITY_MODES,
    ROTATION_MODES,
    ROTATION_OVERLAY_MODES,
)
from trading.services.accounts.config import (  # noqa: F401
    INSTRUMENT_MODES,
    OPTION_TYPES,
    RISK_POLICIES,
)


def fetch_account_by_name(conn: sqlite3.Connection, name: str) -> dict[str, object] | None:
    return _repo_fetch_account_by_name(conn, name)


def fetch_all_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names_from_conn(conn)


def fetch_account_rows_excluding(conn: sqlite3.Connection, *, excluded_name: str) -> list[dict[str, object]]:
    return fetch_account_rows_excluding_name(conn, excluded_name=excluded_name)


def fetch_latest_snapshot_row(conn: sqlite3.Connection, account_id: int) -> dict[str, object] | None:
    return _repo_fetch_latest_snapshot_row(conn, account_id=account_id)


def fetch_snapshot_history_rows(conn: sqlite3.Connection, account_id: int, *, limit: int) -> list[dict[str, object]]:
    return _repo_fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def load_all_account_names() -> list[str]:
    return _repo_fetch_all_account_names()
