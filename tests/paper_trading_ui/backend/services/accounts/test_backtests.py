from __future__ import annotations

from types import SimpleNamespace

from common.time import utc_now_iso
from paper_trading_ui.backend.config import (
    TEST_ACCOUNT_NAME,
    TEST_ACCOUNT_STRATEGY,
    TEST_BACKTEST_ACCOUNT_NAME,
)
from paper_trading_ui.backend.services.accounts import backtests as account_backtests


def test_display_helpers_map_shadow_backtest_account() -> None:
    assert account_backtests.display_account_name(TEST_BACKTEST_ACCOUNT_NAME) == TEST_ACCOUNT_NAME
    assert account_backtests.display_account_name("acct_live") == "acct_live"
    assert account_backtests.display_strategy(TEST_BACKTEST_ACCOUNT_NAME, "trend") == TEST_ACCOUNT_STRATEGY
    assert account_backtests.display_strategy("acct_live", "trend") == "trend"


def test_build_backtest_run_summary_uses_display_transforms() -> None:
    run_dict = {
        "runId": 7,
        "runName": "run-shadow",
        "accountName": TEST_BACKTEST_ACCOUNT_NAME,
        "strategy": "trend",
        "startDate": "2026-01-01",
        "endDate": "2026-01-31",
        "createdAt": "2026-02-01T00:00:00Z",
        "slippageBps": 5.0,
        "feePerTrade": 1.25,
        "tickersFile": "trading/config/trade_universe.txt",
    }

    payload = account_backtests._apply_display_names(run_dict)
    assert payload["runId"] == 7
    assert payload["accountName"] == TEST_ACCOUNT_NAME
    assert payload["strategy"] == TEST_ACCOUNT_STRATEGY
    assert payload["feePerTrade"] == 1.25


def test_fetch_latest_backtest_summary_none_and_present(conn, create_test_account) -> None:
    account_id = create_test_account("acct_bt")

    assert account_backtests.fetch_latest_backtest_summary(conn, "acct_bt") is None

    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            "run-1",
            "2026-01-01",
            "2026-01-31",
            utc_now_iso(),
            5.0,
            0.25,
            "trading/config/trade_universe.txt",
        ),
    )
    conn.commit()

    summary = account_backtests.fetch_latest_backtest_summary(conn, "acct_bt")
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
        (
            account_id,
            "run-metrics",
            "2026-01-01",
            "2026-01-31",
            utc_now_iso(),
            5.0,
            0.0,
            "trading/config/trade_universe.txt",
        ),
    )
    conn.commit()

    monkeypatch.setattr(
        account_backtests,
        "fetch_backtest_report_summary",
        lambda _conn, _run_id: SimpleNamespace(
            run_id=99,
            end_date="2026-01-31",
            total_return_pct=12.5,
            max_drawdown_pct=-4.2,
            sharpe_ratio=1.4,
            sortino_ratio=1.9,
            calmar_ratio=0.8,
            win_rate_pct=57.0,
            profit_factor=1.6,
            avg_trade_return_pct=2.1,
        ),
    )

    payload = account_backtests.fetch_latest_backtest_metrics(conn, "acct_metrics")
    assert payload == {
        "runId": 99,
        "endDate": "2026-01-31",
        "totalReturnPct": 12.5,
        "maxDrawdownPct": -4.2,
        "sharpeRatio": 1.4,
        "sortinoRatio": 1.9,
        "calmarRatio": 0.8,
        "winRatePct": 57.0,
        "profitFactor": 1.6,
        "avgTradeReturnPct": 2.1,
    }
