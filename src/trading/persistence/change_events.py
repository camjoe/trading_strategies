"""The field diff behind the settings change-event trail.

`global_settings` and `book_rotation_settings` each record an audit row per operator
edit, holding the fields whose values actually changed. The diff is the same for both,
so it lives here; the surrounding writes stay in each repository, which owns its own
tables and their keys (`id = 1` against `book_id`, and only the book table's audit row
carries a scope column). Encoding the result is :func:`common.json_columns.dumps_json_column`.

Both repositories build that write the same way — read current, upsert the group's
columns, diff, record the event. Two is similarity, not duplication: collapsing it would
mean parameterizing four table names into a package that owns none. A third settings
table with an audit trail is the point to reconsider.
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
