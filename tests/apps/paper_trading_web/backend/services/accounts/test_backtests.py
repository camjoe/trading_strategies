from __future__ import annotations

from types import SimpleNamespace

from paper_trading_web.backend.services.accounts import backtests as account_backtests

from backtesting.models.report import BacktestRunSummary
from common.time import utc_now_iso


def test_fetch_recent_backtest_run_summaries_maps_records_to_transport_keys(monkeypatch, conn) -> None:
    """camelCase is this layer's job: the backtesting package returns typed records."""
    record = BacktestRunSummary(
        run_id=7,
        run_name="weekly",
        account_name="acct_local",
        strategy="trend",
        start_date="2026-01-01",
        end_date="2026-01-31",
        created_at="2026-02-01T00:00:00Z",
        slippage_bps=5.0,
        fee_per_trade=0.25,
        tickers_file="universe.txt",
    )
    monkeypatch.setattr(account_backtests, "fetch_recent_backtest_runs", lambda _conn, limit: [record])

    assert account_backtests.fetch_recent_backtest_run_summaries(conn, limit=50) == [
        {
            "runId": 7,
            "runName": "weekly",
            "accountName": "acct_local",
            "strategy": "trend",
            "startDate": "2026-01-01",
            "endDate": "2026-01-31",
            "createdAt": "2026-02-01T00:00:00Z",
            "slippageBps": 5.0,
            "feePerTrade": 0.25,
            "tickersFile": "universe.txt",
        }
    ]


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
            "src/infrastructure/config/trade_universes/default.txt",
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
            "src/infrastructure/config/trade_universes/default.txt",
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
