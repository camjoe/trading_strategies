"""Shared helpers for documentation_ui registry builders."""

from __future__ import annotations

from typing import Any, Callable


def sort_registry_rows(
    rows: list[dict[str, Any]],
    secondary_sort_fn: Callable[[dict[str, Any]], object],
) -> None:
    """Sort rows by ``_sort_group`` rank then a secondary key; strip ``_sort_group`` in place."""
    rows.sort(key=lambda item: (int(item["_sort_group"]), secondary_sort_fn(item)))
    for row in rows:
        del row["_sort_group"]
