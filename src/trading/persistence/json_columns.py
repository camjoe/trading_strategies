"""Canonical JSON encoding for values stored in database columns.

One spelling per value: keys sorted, no insignificant whitespace. Rows written by
different code paths into the same column then hold identical text for identical
data, which is what makes a column diffable and what makes any hash taken over its
contents stable.

``sort_keys`` is a no-op for the columns holding a JSON *list* (``trade_symbols``,
``universe_tickers_json``); routing those through the same function anyway means a
caller never has to work out whether it matters for the shape at hand.
"""

from __future__ import annotations

import json

# No insignificant whitespace: the stored text is the value, not a rendering of it.
JSON_COLUMN_SEPARATORS = (",", ":")


def dumps_json_column(value: object) -> str:
    """Encode ``value`` for storage in a JSON text column."""
    return json.dumps(value, separators=JSON_COLUMN_SEPARATORS, sort_keys=True)
