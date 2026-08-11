"""The one wire format for JSON stored in a database column.

One spelling per value: keys sorted, no insignificant whitespace. Rows written by
different code paths into the same column then hold identical text for identical
data, which is what makes a column diffable and what makes any hash taken over its
contents stable.

``sort_keys`` is a no-op for the columns holding a JSON *list* (``trade_symbols``,
``universe_tickers_json``); routing those through the same function anyway means a
caller never has to work out whether it matters for the shape at hand.

Writer and reader live together because they agree on one format: ``row_json_object``
validates the shape ``dumps_json_column`` writes. They sit in ``common`` rather than
``trading/persistence`` because neither needs a connection, and both are reached from
layers that cannot import persistence — ``trading/models`` from below it, and
``backtesting/domain`` from a peer context.

Every JSON *column* write routes through the writer; ``params_fingerprint`` in the
walk-forward optimizer is a SHA-256 over exactly this encoding. Uses that are not column
writes stay on plain ``json.dumps``: the market-data file cache, runtime job artifacts and
log lines, and notification bodies. Those are read by humans or other systems, and several
want ``indent=2``.
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
