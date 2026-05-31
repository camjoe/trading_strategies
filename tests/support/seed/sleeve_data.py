"""Seed module for sleeve data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from tests.support.seed.accounts import ACCT_TREND, seed_account_id

SLEEVE_TREND = "seed_sleeve_core"
SLEEVE_STRATEGY = "trend_v1"
SLEEVE_METRIC_DATE = "2026-01-03"


def seed_sleeves(conn: sqlite3.Connection) -> None:
    from trading.repositories.daily_metrics import DailyMetricsRepository
    from trading.repositories.sleeves import (
        insert_sleeve_strategy_assignment,
        insert_strategy_sleeve,
    )

    acct_id = seed_account_id(conn, ACCT_TREND)
    ts = "2026-01-01T00:00:00Z"
    sleeve_id = insert_strategy_sleeve(
        conn,
        account_id=acct_id,
        name=SLEEVE_TREND,
        status="active",
        base_ccy="USD",
        start_equity=10_000.0,
        current_cash=9_000.0,
        current_equity=10_200.0,
        created_at=ts,
        updated_at=ts,
    )
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name=SLEEVE_STRATEGY,
        param_set_id=None,
        effective_from="2026-01-01",
        effective_to=None,
        is_incumbent=1,
        created_at=ts,
        updated_at=ts,
    )
    DailyMetricsRepository(conn).upsert(
        account_id=acct_id,
        sleeve_id=sleeve_id,
        metric_date=SLEEVE_METRIC_DATE,
        return_pct=1.5,
        drawdown_pct=-2.0,
        turnover_pct=0.1,
        slippage_bps=3.0,
        hit_rate=0.6,
        expectancy=0.8,
        risk_adjusted_score=0.75,
        trade_count=5,
        fees_total=10.0,
        created_at=ts,
        updated_at=ts,
    )


__all__ = [
    "SLEEVE_METRIC_DATE",
    "SLEEVE_STRATEGY",
    "SLEEVE_TREND",
    "seed_sleeves",
]
