"""Shared helpers for analysis service tests."""

from __future__ import annotations

import sqlite3

from trading.services.accounts import create_account
from trading.services.analysis import portfolio as analysis_portfolio


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

        now = utc_now_iso()
        conn.execute(
            "INSERT INTO accounts (name, initial_cash, created_at, updated_at, benchmark_ticker) VALUES (?,?,?,?,?)",
            (name, 0.0, now, now, "SPY"),
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
    from tests.support.fills import seed_fill_event

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker=ticker,
        side="buy",
        qty=qty,
        price=price,
        trade_time=utc_now_iso(),
    )


def patch_analysis_market_data(
    monkeypatch,
    *,
    prices: dict[str, float] | None = None,
    benchmark: tuple[float | None, float | None] = (None, None),
) -> None:
    monkeypatch.setattr(
        analysis_portfolio,
        "fetch_latest_prices",
        lambda _tickers, **_kwargs: prices or {},
    )
    monkeypatch.setattr(
        analysis_portfolio,
        "benchmark_stats",
        lambda _ticker, _effective_initial, _created_at, **_kwargs: benchmark,
    )


__all__ = [
    "make_analysis_account",
    "patch_analysis_market_data",
    "record_analysis_buy",
]
