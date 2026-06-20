from __future__ import annotations
from types import SimpleNamespace

from common.time import utc_now_iso
from paper_trading_web.backend.services.accounts import backtests as account_backtests


def test_fetch_recent_backtest_run_summaries_passthrough(monkeypatch, conn) -> None:
    rows = [{"runId": 7, "accountName": "acct_local", "strategy": "trend"}]
    monkeypatch.setattr(account_backtests, "fetch_recent_backtest_runs", lambda _conn, limit: rows)

    assert account_backtests.fetch_recent_backtest_run_summaries(conn, limit=50) == rows


def test_fetch_latest_backtest_summary_none_and_present(conn, create_account_row) -> None:
    account_id = create_account_row("acct_bt")

    assert account_backtests.fetch_latest_backtest_summary(conn, "acct_bt") is None

    conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id, run_name, start_date, end_date, created_at,
            slippage_bps, fee_per_trade, tickers_file
        )
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
            "src/infrastructure/config/trade_universe.txt",
        ),
    )
    conn.commit()

    summary = account_backtests.fetch_latest_backtest_summary(conn, "acct_bt")
    assert summary is not None
    assert summary["runName"] == "run-1"
    assert summary["accountName"] == "acct_bt"


def test_fetch_latest_backtest_metrics_uses_summary_report(monkeypatch, conn, create_account_row) -> None:
    account_id = create_account_row("acct_metrics")
    conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id, run_name, start_date, end_date, created_at,
            slippage_bps, fee_per_trade, tickers_file
        )
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
            "src/infrastructure/config/trade_universe.txt",
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
