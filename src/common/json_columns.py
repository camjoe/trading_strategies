"""The one wire format for JSON stored in a database column.

One spelling per value: keys sorted, no insignificant whitespace, so identical data
written by different code paths lands as identical text. ``params_fingerprint`` in the
walk-forward optimizer is a SHA-256 over exactly this encoding — the format is not free
to change.

``sort_keys`` is a no-op for the list columns (``trade_symbols``, ``universe_tickers_json``);
routing those through the same function means a caller need not work out whether it
matters for the shape at hand.

Not for JSON that is not a column value: the market-data file cache, job artifacts, log
lines, and notification bodies stay on plain ``json.dumps``, and several want ``indent=2``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

# No insignificant whitespace: the stored text is the value, not a rendering of it.
JSON_COLUMN_SEPARATORS = (",", ":")


def dumps_json_column(value: object) -> str:
    """Encode ``value`` for storage in a JSON text column."""
    return json.dumps(value, separators=JSON_COLUMN_SEPARATORS, sort_keys=True)


def loads_json_object(text: str | None, *, where: str = "") -> dict[str, Any]:
    """Decode an already-extracted JSON *object* column string, rejecting any other shape.

    The string-side counterpart to ``dumps_json_column``: use it when a record
    already holds the column text (e.g. ``record.params_json``). A NULL column
    (``None``) reads as an empty dict; every other text is decoded, so an empty
    or malformed string surfaces as an error rather than being read as ``{}``.
    ``where`` names the source for the error message. Not for nullable-object
    columns whose JSON ``null`` is a valid value — those keep ``json.loads`` so
    the ``null`` decodes rather than raising.
    """
    if text is None:
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        location = f" in {where}" if where else ""
        raise ValueError(f"Expected a JSON object{location}.")
    return payload


def row_json_object(row: Mapping[str, object], key: str) -> dict[str, Any]:
    """Decode a JSON *object* column from a row mapping (see ``loads_json_object``).

    Returns ``dict[str, Any]`` because a decoded payload's value types are only
    known to its caller; the guard here is the outer shape, which several callers
    would otherwise assume. A NULL column reads as an empty dict.
    """
    raw = row[key]
    return loads_json_object(None if raw is None else str(raw), where=f"column '{key}'")
