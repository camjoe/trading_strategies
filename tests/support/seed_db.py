"""
Shared session-level test database seed module.

``seed_session_db(conn)`` populates a freshly initialised database with a
canonical, named dataset that covers the most common test scenarios across
the repository and service test suites.

Usage convention
----------------
Tests that only *read* or *filter* data should accept the ``seeded_conn``
fixture (session-scoped) instead of the per-test ``conn`` fixture.  Tests
that write, delete, or depend on an empty-table state must continue using
the function-scoped ``conn`` fixture so they get an isolated database.

The seed data is **read-only by convention**.  Nothing enforces this at the
SQLite level, so mutating the seeded connection from a test will silently
corrupt the shared state for all subsequent tests in that worker.

Named constants
---------------
Import these constants in test modules to reference seeded entities without
hard-coding string literals:

    from tests.support.seed_db import ACCT_TREND, ACCT_MOMENTUM, ACCT_LOCAL

"""
from __future__ import annotations

import sqlite3

from trading.services.accounts import create_account

# ---------------------------------------------------------------------------
# Public name constants — use these in tests instead of raw strings
# ---------------------------------------------------------------------------

# Managed accounts
ACCT_TREND = "seed_trend"
ACCT_MOMENTUM = "seed_momentum"

# Local (non-managed) account
ACCT_LOCAL = "seed_local"

# Trades seeded under ACCT_TREND
TRADE_BUY_AAPL = "AAPL"
TRADE_BUY_MSFT = "MSFT"
TRADE_SELL_AAPL = "AAPL"

# Snapshot timestamps seeded under ACCT_TREND
SNAPSHOT_T1 = "2026-01-01T00:00:00"
SNAPSHOT_T2 = "2026-01-02T00:00:00"
SNAPSHOT_T3 = "2026-01-03T00:00:00"

# Backtest run name seeded under ACCT_TREND
BACKTEST_RUN_NAME = "seed_run_a"

# Promotion review strategy seeded under ACCT_TREND
PROMOTION_STRATEGY = "trend_v1"


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def seed_session_db(conn: sqlite3.Connection) -> None:
    """Populate *conn* with the canonical session-level dataset.

    Call this exactly once per session (the ``seeded_conn`` fixture does
    this automatically).  Do not call it from individual tests.
    """
    _seed_accounts(conn)
    _seed_trades(conn)
    _seed_snapshots(conn)
    _seed_global_settings(conn)
    _seed_backtest_run(conn)
    _seed_promotion_review(conn)
    conn.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _account_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    assert row is not None, f"seed account '{name}' not found"
    return int(row["id"])


def _seed_accounts(conn: sqlite3.Connection) -> None:
    create_account(conn, ACCT_TREND, "trend_v1", 10_000.0, "SPY")
    create_account(conn, ACCT_MOMENTUM, "momentum_v1", 8_000.0, "QQQ")
    from trading.models import AccountConfig
    create_account(
        conn,
        ACCT_LOCAL,
        "trend_v1",
        5_000.0,
        "SPY",
        config=AccountConfig(account_kind="local"),
    )


def _seed_trades(conn: sqlite3.Connection) -> None:
    acct_id = _account_id(conn, ACCT_TREND)
    conn.executemany(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (acct_id, TRADE_BUY_AAPL, "buy", 10.0, 150.0, 0.0, "2026-01-02T10:00:00", "entry"),
            (acct_id, TRADE_BUY_MSFT, "buy", 5.0, 300.0, 0.0, "2026-01-03T10:00:00", "entry"),
            (acct_id, TRADE_SELL_AAPL, "sell", 10.0, 160.0, 0.0, "2026-01-10T10:00:00", "exit"),
        ],
    )


def _seed_snapshots(conn: sqlite3.Connection) -> None:
    acct_id = _account_id(conn, ACCT_TREND)
    conn.executemany(
        """
        INSERT INTO equity_snapshots
            (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (acct_id, SNAPSHOT_T1, 9_500.0, 500.0, 10_000.0, 0.0, 0.0),
            (acct_id, SNAPSHOT_T2, 9_200.0, 800.0, 10_050.0, 0.0, 50.0),
            (acct_id, SNAPSHOT_T3, 9_000.0, 1_100.0, 10_100.0, 100.0, 50.0),
        ],
    )


def _seed_global_settings(conn: sqlite3.Connection) -> None:
    # Insert a minimal global_settings row using the default values; all
    # columns have schema-level defaults so only the primary key is needed.
    conn.execute("INSERT OR IGNORE INTO global_settings (id) VALUES (1)")


def _seed_backtest_run(conn: sqlite3.Connection) -> None:
    acct_id = _account_id(conn, ACCT_TREND)
    conn.execute(
        """
        INSERT INTO backtest_runs
            (account_id, strategy_name, run_name, start_date, end_date, created_at,
             slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            acct_id,
            PROMOTION_STRATEGY,
            BACKTEST_RUN_NAME,
            "2025-07-01",
            "2025-12-31",
            "2026-01-01T00:00:00Z",
            5.0,
            0.0,
            "trading/config/trade_universe.txt",
        ),
    )


def _seed_promotion_review(conn: sqlite3.Connection) -> None:
    from trading.domain.evaluation_models import (
        EvaluationBacktestEvidence,
        EvaluationBasicScope,
        EvaluationConfidence,
        StrategyEvaluationArtifact,
    )
    from trading.domain.promotion_models import PromotionAssessment
    from trading.repositories.promotion import insert_promotion_review

    acct_id = _account_id(conn, ACCT_TREND)

    evaluation = StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(
            account_id=acct_id,
            account_name=ACCT_TREND,
            requested_strategy=PROMOTION_STRATEGY,
            live_trading_enabled=False,
        ),
        backtest=EvaluationBacktestEvidence(
            available=True,
            trade_count=15,
            snapshot_count=30,
            total_return_pct=4.5,
            max_drawdown_pct=-8.0,
        ),
        confidence=EvaluationConfidence(overall_confidence=0.82),
    )
    assessment = PromotionAssessment(
        account_name=ACCT_TREND,
        strategy_name=PROMOTION_STRATEGY,
        stage="promotion_review",
        status="ready_for_review",
        ready_for_live=True,
        overall_confidence=0.82,
        next_action="Request operator review.",
    )
    insert_promotion_review(
        conn,
        assessment=assessment,
        evaluation=evaluation,
        requested_by="seed",
        operator_summary_note="",
        created_at="2026-01-15T00:00:00Z",
    )


__all__ = [
    "ACCT_LOCAL",
    "ACCT_MOMENTUM",
    "ACCT_TREND",
    "BACKTEST_RUN_NAME",
    "PROMOTION_STRATEGY",
    "SNAPSHOT_T1",
    "SNAPSHOT_T2",
    "SNAPSHOT_T3",
    "TRADE_BUY_AAPL",
    "TRADE_BUY_MSFT",
    "TRADE_SELL_AAPL",
    "seed_session_db",
]
