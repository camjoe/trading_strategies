"""Create the deterministic synthetic story used by the offline web demo."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timezone

import pandas as pd

from trading.models import AccountConfig
from trading.repositories.demo_seed import DemoSeedRepository
from trading.repositories.unit_of_work import unit_of_work
from trading.services.accounts import create_account, get_account
from trading.services.analysis.daily_metrics import write_daily_metrics_for_account

TREND_ACCOUNT = "demo_trend"
MOMENTUM_ACCOUNT = "demo_momentum"
SNAPSHOT_BUSINESS_DAYS = 30


def seed_demo_database(conn: sqlite3.Connection, *, anchor_date: date | None = None) -> None:
    """Atomically seed two safe paper accounts and their synthetic evidence."""
    anchor = anchor_date or datetime.now(timezone.utc).date()
    business_days = list(pd.bdate_range(end=anchor, periods=SNAPSHOT_BUSINESS_DAYS))
    now_iso = datetime.combine(anchor, time(hour=16), tzinfo=timezone.utc).isoformat()

    with unit_of_work(conn):
        create_account(conn, TREND_ACCOUNT, "trend_v1", 10_000.0, "SPY", AccountConfig(descriptive_name="Demo Trend"))
        create_account(
            conn, MOMENTUM_ACCOUNT, "momentum_v1", 12_000.0, "QQQ", AccountConfig(descriptive_name="Demo Momentum")
        )
        repo = DemoSeedRepository(conn)
        for account_name in (TREND_ACCOUNT, MOMENTUM_ACCOUNT):
            account_id = repo.account_id(account_name)
            repo.set_account_demo_safety(account_id, now_iso=now_iso)

        trend_id = repo.account_id(TREND_ACCOUNT)
        momentum_id = repo.account_id(MOMENTUM_ACCOUNT)
        trend_book = repo.default_book_id(trend_id)
        momentum_book = repo.default_book_id(momentum_id)

        fill_dates = [business_days[2], business_days[8], business_days[20], business_days[4], business_days[16]]
        for account_id, book_id, symbol, side, qty, price, stamp in [
            (trend_id, trend_book, "AAPL", "buy", 10.0, 150.0, fill_dates[0]),
            (trend_id, trend_book, "MSFT", "buy", 5.0, 300.0, fill_dates[1]),
            (trend_id, trend_book, "AAPL", "sell", 4.0, 161.0, fill_dates[2]),
            (momentum_id, momentum_book, "NVDA", "buy", 8.0, 120.0, fill_dates[3]),
            (momentum_id, momentum_book, "NVDA", "sell", 3.0, 116.0, fill_dates[4]),
        ]:
            repo.insert_fill(
                account_id=account_id,
                book_id=book_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                time_iso=stamp.isoformat(),
            )

        repo.upsert_position(book_id=trend_book, symbol="AAPL", qty=6, avg_cost=150, market_value=990, now_iso=now_iso)
        repo.upsert_position(
            book_id=trend_book, symbol="MSFT", qty=5, avg_cost=300, market_value=1585, now_iso=now_iso
        )
        repo.upsert_position(
            book_id=momentum_book, symbol="NVDA", qty=5, avg_cost=120, market_value=575, now_iso=now_iso
        )

        trend_curve: list[tuple[str, float]] = []
        for index, stamp in enumerate(business_days):
            trend_equity = 10_000.0 + index * 21.0 + ((index % 5) - 2) * 18.0
            momentum_equity = 12_000.0 + index * 6.0 + ((index % 6) - 3) * 31.0
            date_text = stamp.date().isoformat()
            trend_curve.append((date_text, trend_equity))
            repo.insert_snapshot(
                book_id=trend_book,
                time_iso=stamp.isoformat(),
                cash=7_500,
                market_value=2_575,
                equity=trend_equity,
                realized=44,
            )
            repo.insert_snapshot(
                book_id=momentum_book,
                time_iso=stamp.isoformat(),
                cash=11_350,
                market_value=575,
                equity=momentum_equity,
                realized=-12,
            )

        # Derive daily_metrics through the real production writer over the seeded
        # snapshots and fills, so the demo exercises the same code path as runtime
        # and can never show numbers the live system cannot produce.
        trend_account = get_account(conn, TREND_ACCOUNT)
        momentum_account = get_account(conn, MOMENTUM_ACCOUNT)
        for date_text, _equity in trend_curve:
            write_daily_metrics_for_account(conn, trend_account, metric_date=date_text, now_iso=now_iso)
            write_daily_metrics_for_account(conn, momentum_account, metric_date=date_text, now_iso=now_iso)

        repo.insert_backtest(
            account_id=trend_id,
            strategy_key="trend_v1",
            start_date=trend_curve[0][0],
            end_date=trend_curve[-1][0],
            snapshots=trend_curve,
            now_iso=now_iso,
        )
        repo.insert_promotion_review(
            account_id=trend_id, account_name=TREND_ACCOUNT, strategy_key="trend_v1", now_iso=now_iso
        )
        repo.finish()
