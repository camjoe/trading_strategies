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


def row_json_object(row: Mapping[str, object], key: str) -> dict[str, Any]:
    """Decode a JSON *object* column, rejecting any other shape.

    Returns ``dict[str, Any]`` because a decoded payload's value types are only
    known to its caller; the guard here is the outer shape, which several callers
    would otherwise assume. A NULL column reads as an empty dict.
    """
    raw = row[key]
    if raw is None:
        return {}
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in column '{key}'.")
    return payload
