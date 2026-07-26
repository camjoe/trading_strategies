"""Operator-facing printed view of the unified parameter source.

Presentation only: the payload assembly lives in
``trading.services.parameters.view``.
"""

from __future__ import annotations

import sqlite3

from trading.models.books.book_rotation_settings_change_event import BookRotationSettingsChangeEvent
from trading.models.parameters.parameter_source_view import ParameterSourceView
from trading.services.parameters.history import fetch_book_rotation_change_history
from trading.services.parameters.view import fetch_parameter_source_view


def show_parameters(conn: sqlite3.Connection, account_name: str | None = None) -> ParameterSourceView:
    """Print the unified parameter view and return the payload."""
    view = fetch_parameter_source_view(conn, account_name=account_name)

    print("Unified parameter source (read-through view; values live in their own stores):")
    for group in view.groups:
        print(f"[{group.scope}]")
        if group.note is not None:
            print(f"  ({group.note})")
        for entry in group.entries:
            print(f"  {entry.name} = {entry.value} ({entry.source})")
    return view


def show_book_rotation_history(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    limit: int = 20,
) -> list[BookRotationSettingsChangeEvent]:
    """Print a book's rotation settings change-audit trail (latest first) and return it."""
    events = fetch_book_rotation_change_history(conn, account_name=account_name, book_name=book_name, limit=limit)
    if not events:
        print(f"No rotation settings changes recorded for account {account_name}.")
        return events

    print(f"Rotation settings change history (latest {limit}) for account {account_name}:")
    for event in events:
        rendered = ", ".join(
            f"{field}: {change['old']!r} -> {change['new']!r}" for field, change in event.changed_fields.items()
        )
        print(f"- {event.created_at} | {event.settings_group} | {rendered}")
    return events


__all__ = ["show_book_rotation_history", "show_parameters"]
