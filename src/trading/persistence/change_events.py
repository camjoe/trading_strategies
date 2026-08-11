"""The field diff behind the settings change-event trail.

`global_settings` and `book_rotation_settings` each record an audit row per operator
edit, holding the fields whose values actually changed. Encoding the result for its
column is :func:`common.json_columns.dumps_json_column`.
"""

from __future__ import annotations

from collections.abc import Mapping


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
