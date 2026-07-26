"""Edit workflows for the unified parameter source.

Owns the targeted book rotation edits (policy and scheduling): resolve the
account's book, merge the provided fields over the persisted row, and write
it back. Global operational settings edits live in
``trading.services.operational_settings.mutations``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError
from trading.domain.rotation.schedule import dump_rotation_schedule, parse_rotation_schedule
from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.books.book_rotation_settings_record import BookRotationSettingsRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository

# The book rotation-policy fields an operator may set; None clears a field back
# to the RotationPolicyConfig code default. cost_penalty_weight is deliberately
# excluded: its score component has no honest data source (backtest returns are
# already net of per-trade fees, so a separate penalty would double-count), so
# tuning it would have no effect. Its column is still persisted for a possible
# future un-modeled-cost implementation, but is not exposed as tunable.
# regime_fit_weight is settable: regime_fit now computes a real value (see
# docs/reference/rotation-scoring.md).
ROTATION_POLICY_FIELDS = (
    "min_trades_in_window",
    "outperformance_threshold_bps",
    "cooldown_days",
    "risk_adjusted_return_weight",
    "stability_weight",
    "drawdown_penalty_weight",
    "regime_fit_weight",
)

# Every rotation-policy column persisted on book_rotation_settings. The merge
# that feeds the repository upsert must supply all of them, including the inert
# weight above (carried through from the existing row rather than set).
_PERSISTED_ROTATION_POLICY_FIELDS = (
    *ROTATION_POLICY_FIELDS,
    "cost_penalty_weight",
)

# The book rotation-scheduling fields the edit command may touch (book-owned,
# ADR 014); None clears schedule/lookback back to the code default.
ROTATION_SCHEDULING_FIELDS = (
    "rotation_enabled",
    "rotation_schedule",
    "rotation_lookback_days",
)


def _resolve_book_id(conn: sqlite3.Connection, *, account_name: str, book_name: str | None) -> int:
    account = AccountRepository(conn).fetch_by_name(account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")
    if book_name is None:
        # The default book is bootstrapped on first write; an edit is a write.
        book_id = default_book_id(conn, account.id)
        conn.commit()
        return book_id
    for book in BookRepository(conn).fetch_for_account(account_id=account.id):
        if book.name == book_name:
            return book.id
    raise NotFoundError(f"Book not found for account {account_name}: {book_name}")


def update_book_rotation_policy(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    updates: Mapping[str, int | float | None],
) -> BookRotationSettingsRecord:
    """Merge ``updates`` over the book's persisted rotation policy and save.

    Only keys from ``ROTATION_POLICY_FIELDS`` are accepted; a None value
    clears the field back to the code default. Returns the persisted row.
    """
    unknown = sorted(set(updates) - set(ROTATION_POLICY_FIELDS))
    if unknown:
        raise ValueError(f"Unknown rotation policy fields: {', '.join(unknown)}")
    if not updates:
        raise ValueError("No rotation policy fields provided.")

    book_id = _resolve_book_id(conn, account_name=account_name, book_name=book_name)
    repository = BookRotationSettingsRepository(conn)
    current = repository.fetch(book_id=book_id)
    merged = {
        name: updates[name] if name in updates else (getattr(current, name) if current is not None else None)
        for name in _PERSISTED_ROTATION_POLICY_FIELDS
    }
    now_iso = utc_now_iso()
    repository.upsert_rotation_policy(
        book_id=book_id,
        created_at=current.created_at if current is not None else now_iso,
        updated_at=now_iso,
        **merged,
    )
    saved = repository.fetch(book_id=book_id)
    if saved is None:
        raise RuntimeError(f"book_rotation_settings row missing after upsert for book_id={book_id}")
    return saved


def update_book_rotation_scheduling(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    updates: Mapping[str, object],
) -> BookRotationSettingsRecord:
    """Merge ``updates`` over the book's persisted rotation scheduling and save.

    Only keys from ``ROTATION_SCHEDULING_FIELDS`` are accepted.
    ``rotation_schedule`` takes a list of strategy names (validated) or None
    for no challengers; ``rotation_lookback_days`` None falls back to the code
    default. Returns the persisted row.
    """
    unknown = sorted(set(updates) - set(ROTATION_SCHEDULING_FIELDS))
    if unknown:
        raise ValueError(f"Unknown rotation scheduling fields: {', '.join(unknown)}")
    if not updates:
        raise ValueError("No rotation scheduling fields provided.")

    book_id = _resolve_book_id(conn, account_name=account_name, book_name=book_name)
    repository = BookRotationSettingsRepository(conn)
    current = repository.fetch(book_id=book_id)

    if "rotation_enabled" in updates:
        enabled = int(bool(updates["rotation_enabled"]))
    else:
        enabled = int(current.rotation_enabled) if current is not None else 0
    if "rotation_lookback_days" in updates:
        raw_lookback = updates["rotation_lookback_days"]
        if raw_lookback is None:
            lookback = None
        elif isinstance(raw_lookback, int):
            lookback = raw_lookback
        else:
            raise ValueError("rotation_lookback_days must be an integer or None")
        if lookback is not None and lookback <= 0:
            raise ValueError("rotation_lookback_days must be > 0")
    else:
        lookback = current.rotation_lookback_days if current is not None else None
    if "rotation_schedule" in updates:
        names = parse_rotation_schedule(updates["rotation_schedule"])
        for name in names:
            validate_strategy_name(name)
        schedule = dump_rotation_schedule(names) if names else None
    else:
        schedule = current.rotation_schedule if current is not None else None

    now_iso = utc_now_iso()
    repository.upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=enabled,
        rotation_lookback_days=lookback,
        rotation_schedule=schedule,
        created_at=current.created_at if current is not None else now_iso,
        updated_at=now_iso,
    )
    saved = repository.fetch(book_id=book_id)
    if saved is None:
        raise RuntimeError(f"book_rotation_settings row missing after upsert for book_id={book_id}")
    return saved
