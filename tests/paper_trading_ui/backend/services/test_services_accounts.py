from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.time import utc_now_iso
from paper_trading_ui.backend.services import accounts as services_accounts
from paper_trading_ui.backend.config import (
    TEST_ACCOUNT_NAME,
    TEST_ACCOUNT_STRATEGY,
    TEST_BACKTEST_ACCOUNT_NAME,
)


def test_build_account_summary_uses_snapshot_delta(monkeypatch) -> None:
    monkeypatch.setattr(
        services_accounts,
        "build_account_stats",
        lambda _conn, _row: (None, None, None, None, 1200.0),
    )
    monkeypatch.setattr(
        services_accounts,
        "fetch_latest_snapshot_row",
        lambda _conn, _account_id: {"equity": 1100.0, "snapshot_time": "2026-01-02T00:00:00Z"},
    )

    summary = services_accounts.build_account_summary(
        conn=None,
        row={
            "id": 1,
            "name": "acct_a",
            "descriptive_name": "Account A",
            "strategy": "trend",
            "instrument_mode": "equity",
            "risk_policy": "none",
            "benchmark_ticker": "SPY",
            "initial_cash": 1000.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "goal_min_return_pct": None,
            "goal_max_return_pct": None,
            "goal_period": None,
            "learning_enabled": None,
            "option_strike_offset_pct": None,
            "option_min_dte": None,
            "option_max_dte": None,
            "option_type": None,
            "target_delta_min": None,
            "target_delta_max": None,
            "max_premium_per_trade": None,
            "max_contracts_per_trade": None,
            "iv_rank_min": None,
            "iv_rank_max": None,
            "roll_dte_threshold": None,
            "profit_take_pct": None,
            "max_loss_pct": None,
        },
    )

    assert summary["equity"] == 1200.0
    assert summary["totalChange"] == 200.0
    assert summary["totalChangePct"] == pytest.approx(20.0)
    assert summary["changeSinceLastSnapshot"] == 100.0


def test_display_helpers_map_shadow_backtest_account() -> None:
    assert services_accounts.display_account_name(TEST_BACKTEST_ACCOUNT_NAME) == TEST_ACCOUNT_NAME
    assert services_accounts.display_account_name("acct_live") == "acct_live"
    assert services_accounts.display_strategy(TEST_BACKTEST_ACCOUNT_NAME, "trend") == TEST_ACCOUNT_STRATEGY
    assert services_accounts.display_strategy("acct_live", "trend") == "trend"


def test_build_backtest_run_summary_uses_display_transforms(conn) -> None:
    row = conn.execute(
        """
        SELECT
            7 AS id,
            'run-shadow' AS run_name,
            '2026-01-01' AS start_date,
            '2026-01-31' AS end_date,
            '2026-02-01T00:00:00Z' AS created_at,
            5.0 AS slippage_bps,
            1.25 AS fee_per_trade,
            'trading/config/trade_universe.txt' AS tickers_file,
            ? AS account_name,
            'trend' AS strategy
        """,
        (TEST_BACKTEST_ACCOUNT_NAME,),
    ).fetchone()

    payload = services_accounts.build_backtest_run_summary(row)
    assert payload["runId"] == 7
    assert payload["accountName"] == TEST_ACCOUNT_NAME
    assert payload["strategy"] == TEST_ACCOUNT_STRATEGY
    assert payload["feePerTrade"] == 1.25


def test_fetch_managed_account_rows_excludes_shadow_account(conn, create_test_account) -> None:
    create_test_account("acct_one")
    create_test_account(TEST_BACKTEST_ACCOUNT_NAME)
    create_test_account("acct_two")

    rows = services_accounts.fetch_managed_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_one", "acct_two"]


def test_fetch_latest_backtest_summary_none_and_present(conn, create_test_account) -> None:
    account_id = create_test_account("acct_bt")

    assert services_accounts.fetch_latest_backtest_summary(conn, "acct_bt") is None

    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "run-1", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.25, "trading/config/trade_universe.txt"),
    )
    conn.commit()

    summary = services_accounts.fetch_latest_backtest_summary(conn, "acct_bt")
    assert summary is not None
    assert summary["runName"] == "run-1"
    assert summary["accountName"] == "acct_bt"


def test_fetch_latest_backtest_metrics_uses_summary_report(monkeypatch, conn, create_test_account) -> None:
    account_id = create_test_account("acct_metrics")
    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "run-metrics", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.0, "trading/config/trade_universe.txt"),
    )
    conn.commit()

    monkeypatch.setattr(
        services_accounts,
        "fetch_backtest_report_summary",
        lambda _conn, _run_id: SimpleNamespace(
            run_id=99,
            end_date="2026-01-31",
            total_return_pct=12.5,
            max_drawdown_pct=-4.2,
        ),
    )

    payload = services_accounts.fetch_latest_backtest_metrics(conn, "acct_metrics")
    assert payload == {
        "runId": 99,
        "endDate": "2026-01-31",
        "totalReturnPct": 12.5,
        "maxDrawdownPct": -4.2,
        "alphaPct": None,
    }
