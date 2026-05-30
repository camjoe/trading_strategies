from __future__ import annotations

import sqlite3

from trading.repositories.daily_metrics import fetch_daily_metrics_for_sleeve_window


def fetch_sleeve_performance_window(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    if sleeve_id <= 0:
        raise ValueError("sleeve_id must be positive.")
    return fetch_daily_metrics_for_sleeve_window(
        conn,
        sleeve_id=sleeve_id,
        start_date=start_date,
        end_date=end_date,
    )
