"""Book performance query flows for analysis consumers.

Owns read-only book performance-window reads beneath the stable
``trading.services.analysis`` package surface.
"""

from __future__ import annotations

import sqlite3

from trading.models.portfolio import DailyMetricRecord
from trading.repositories.daily_metrics import DailyMetricsRepository


def fetch_book_performance_window(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    start_date: str,
    end_date: str,
) -> list[DailyMetricRecord]:
    if book_id <= 0:
        raise ValueError("book_id must be positive.")
    return DailyMetricsRepository(conn).fetch_for_book_window(
        book_id=book_id,
        start_date=start_date,
        end_date=end_date,
    )
