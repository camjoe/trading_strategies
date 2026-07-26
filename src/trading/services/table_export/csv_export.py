from __future__ import annotations

import csv
import io
import sqlite3
from typing import Iterator

from trading.repositories.table_export import fetch_table_cursor


def stream_table_csv(conn: sqlite3.Connection, table: str) -> Iterator[str]:
    _normalized, headers, cur = fetch_table_cursor(conn, table)

    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def _flush() -> str:
        chunk = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return chunk

    if headers:
        writer.writerow(headers)
        yield _flush()

    for row in cur:
        writer.writerow(list(row))
        yield _flush()
