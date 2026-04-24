from pathlib import Path

import pandas as pd
import pytest

import trading.backtesting.backtest as backtest_module
import trading.backtesting.services.execution_service as execution_service
from trading.backtesting.report_models import (
    BacktestFullReport,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
)
from tests.support import (
    create_backtest_account,
    install_backtest_market_data,
    make_backtest_config,
)


class TestBacktestRunFlow:
    def test_run_backtest_persists_isolated_results(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_bt")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL", "MSFT"], benchmark_values=[100.0, 103.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_bt", run_name="smoke"),
        )

        assert result.run_id > 0
        assert result.trade_count > 0

        row = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE id = ?", (result.run_id,)).fetchone()
        assert row is not None and int(row["n"]) == 1

        snapshots = conn.execute(
            "SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert snapshots is not None and int(snapshots["n"]) >= 2

        paper_trades = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()
        assert paper_trades is not None and int(paper_trades["n"]) == 0

    def test_run_backtest_leaps_adds_financial_risk_warnings(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(
            conn,
            "acct_leaps_bt",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 102.0])

        result_without_opt_in = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_leaps_bt"),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result_without_opt_in.warnings)
        assert any("LEAPs approximation opt-in was not enabled" in warning for warning in result_without_opt_in.warnings)

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_leaps_bt", run_name="approx-ok", allow_approximate_leaps=True),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result.warnings)
        assert not any("opt-in was not enabled" in warning for warning in result.warnings)

    def test_backtest_report_returns_summary(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_report_bt")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 105.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_report_bt", slippage_bps=1.0, run_name="for-report"),
        )

        summary = backtest_module.backtest_report(conn, result.run_id)
        assert summary["run_id"] == result.run_id
        assert summary["account_name"] == "acct_report_bt"
        assert summary["trade_count"] >= 0
        assert isinstance(summary["total_return_pct"], float)

    def test_run_backtest_uses_account_trade_size_pct(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_bt_size_small", trade_size_pct=5.0, max_position_pct=10.0)
        create_backtest_account(conn, "acct_bt_size_large", trade_size_pct=15.0, max_position_pct=30.0)
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 105.0])

        small = backtest_module.run_backtest(conn, make_backtest_config("acct_bt_size_small", run_name="small"))
        large = backtest_module.run_backtest(conn, make_backtest_config("acct_bt_size_large", run_name="large"))

        small_qty = float(
            conn.execute(
                "SELECT qty FROM backtest_trades WHERE run_id = ? AND side = 'buy' ORDER BY id ASC LIMIT 1",
                (small.run_id,),
            ).fetchone()["qty"]
        )
        large_qty = float(
            conn.execute(
                "SELECT qty FROM backtest_trades WHERE run_id = ? AND side = 'buy' ORDER BY id ASC LIMIT 1",
                (large.run_id,),
            ).fetchone()["qty"]
        )

        assert small_qty < large_qty

    def test_backtest_report_summary_returns_model(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_report_model")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 104.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_report_model", run_name="for-report-model"),
        )

        summary = backtest_module.backtest_report_summary(conn, result.run_id)
        assert isinstance(summary, BacktestReportSummary)
        assert summary.run_id == result.run_id
        assert summary.account_name == "acct_report_model"

    def test_backtest_report_full_returns_typed_model_and_payload(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_report_full")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 104.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_report_full", run_name="for-report-full"),
        )

        report = backtest_module.backtest_report_full(conn, result.run_id)
        assert isinstance(report, BacktestFullReport)
        assert isinstance(report.summary, BacktestReportSummary)
        assert report.summary.run_id == result.run_id
        assert report.summary.account_name == "acct_report_full"
        assert isinstance(report.snapshots, list)
        assert isinstance(report.trades, list)
        if report.snapshots:
            assert isinstance(report.snapshots[0], BacktestReportSnapshot)
        if report.trades:
            assert isinstance(report.trades[0], BacktestReportTrade)

        payload = report.to_payload()
        legacy_payload = backtest_module.backtest_report(conn, result.run_id)
        assert payload == legacy_payload

    def test_backtest_report_and_leaderboard_use_run_strategy_snapshot(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        create_backtest_account(conn, "acct_strategy_snapshot")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 104.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_strategy_snapshot", slippage_bps=1.0, run_name="strategy-snapshot"),
        )

        conn.execute("UPDATE accounts SET strategy = ? WHERE name = ?", ("mean_reversion", "acct_strategy_snapshot"))
        conn.commit()

        summary = backtest_module.backtest_report(conn, result.run_id)
        assert summary["strategy"] == "trend_v1"

        filtered = backtest_module.backtest_leaderboard(conn, limit=10, strategy="trend_v1")
        assert any(row["run_id"] == result.run_id for row in filtered)

    def test_run_backtest_uses_strategy_signal_resolver(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_sig", strategy="macd_trend")

        call_count = {"n": 0}

        def fake_signal(_strategy_name: str, _history: pd.Series) -> str:
            call_count["n"] += 1
            return "hold"

        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 101.0])
        monkeypatch.setattr(execution_service, "resolve_signal", fake_signal)

        backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_sig", run_name="sig-resolver"),
        )

        assert call_count["n"] > 0

    def test_run_backtest_monthly_universe_reconstitution_adds_warning(
        self,
        conn,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        create_backtest_account(conn, "acct_universe")

        history_dir = tmp_path / "universe_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "2026-01.txt").write_text("AAPL\n", encoding="utf-8")

        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL", "MSFT"], benchmark_values=[100.0, 101.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config(
                "acct_universe",
                universe_history_dir=str(history_dir),
                run_name="universe-reconstitution",
            ),
        )

        assert any("Monthly universe reconstitution enabled" in warning for warning in result.warnings)
        assert any("Universe snapshot missing" in warning for warning in result.warnings)
