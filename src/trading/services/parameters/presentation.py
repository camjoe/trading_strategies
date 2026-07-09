"""Operator-facing printed view of the unified parameter source.

Presentation only: the payload assembly lives in
``trading.services.parameters.view``.
"""

from __future__ import annotations

import sqlite3

from trading.models.parameters.parameter_source_view import ParameterSourceView
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


__all__ = ["show_parameters"]
