"""Canonical JSON encoding for values stored in database columns.

One spelling per value: keys sorted, no insignificant whitespace. Rows written by
different code paths into the same column then hold identical text for identical
data, which is what makes a column diffable and what makes any hash taken over its
contents stable — see ``params_fingerprint`` in
``backtesting.domain.optimization.search``.

``sort_keys`` is a no-op for the columns holding a JSON *list* (``trade_symbols``,
``universe_tickers_json``); routing those through the same function anyway means a
caller never has to work out whether it matters for the shape at hand.
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


def read_json_object(row: Mapping[str, object], key: str) -> dict[str, Any]:
    """Decode a JSON *object* column, rejecting any other shape.

    Returns ``dict[str, Any]`` because a decoded payload's value types are only
    known to its caller; the guard here is the outer shape, which several callers
    would otherwise assume.
    """
    raw = row[key]
    if raw is None:
        return {}
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in column '{key}'.")
    return payload
