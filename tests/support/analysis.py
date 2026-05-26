"""Shared helpers for analysis service tests."""

from __future__ import annotations

import sqlite3

from trading.services.accounts import create_account
from trading.services.analysis import queries as analysis_queries


def make_analysis_account(
    conn: sqlite3.Connection,
    name: str,
    *,
    initial_cash: float = 1000.0,
) -> sqlite3.Row:
    if initial_cash > 0:
        create_account(conn, name, "trend", initial_cash, "SPY")
    else:
        from common.time import utc_now_iso

        conn.execute(
            "INSERT INTO accounts (name, strategy, initial_cash, created_at, benchmark_ticker) VALUES (?,?,?,?,?)",
            (name, "trend", 0.0, utc_now_iso(), "SPY"),
        )
        conn.commit()
    row = conn.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return row


def record_analysis_buy(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    ticker: str,
    qty: float,
    price: float,
) -> None:
    from common.time import utc_now_iso

    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note) VALUES (?,?,?,?,?,?,?,?)",
        (account_id, ticker, "buy", qty, price, 0.0, utc_now_iso(), None),
    )
    conn.commit()


def patch_analysis_market_data(
    monkeypatch,
    *,
    prices: dict[str, float] | None = None,
    benchmark: tuple[float | None, float | None] = (None, None),
) -> None:
    monkeypatch.setattr(
        analysis_queries,
        "fetch_latest_prices",
        lambda _tickers: prices or {},
    )
    monkeypatch.setattr(
        analysis_queries,
        "benchmark_stats",
        lambda _ticker, _effective_initial, _created_at: benchmark,
    )


__all__ = [
    "make_analysis_account",
    "patch_analysis_market_data",
    "record_analysis_buy",
]
