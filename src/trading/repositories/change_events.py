"""Shared pieces of the settings change-event trail.

`global_settings` and `book_rotation_settings` each record an audit row per
operator edit: the fields whose values actually changed, as compact JSON,
tagged with the settings group. The diff and the JSON column encoding are the
same for both; only the table and its scope column differ, so each repository
keeps its own literal SQL and shares the helpers here.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

# Compact JSON storage keeps persisted change-event payloads stable and easy to diff.
JSON_COMPACT_SEPARATORS = (",", ":")


def json_object_dumps(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, separators=JSON_COMPACT_SEPARATORS, sort_keys=True)


def row_json_object(row: sqlite3.Row, key: str) -> dict[str, dict[str, object]]:
    return json.loads(str(row[key]))


def diff_changed_fields(*, current: object | None, new_values: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Old/new pairs for the fields of ``new_values`` that differ from ``current``.

    A missing ``current`` (no settings row yet) reads every old value as None,
    so the first write records the whole group as changed.
    """
    changed: dict[str, dict[str, object]] = {}
    for field_name, new_value in new_values.items():
        old_value = getattr(current, field_name) if current is not None else None
        if old_value != new_value:
            changed[field_name] = {"old": old_value, "new": new_value}
    return changed
