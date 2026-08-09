from pathlib import Path

import pandas as pd
import pytest

import backtesting.composition as composition
import backtesting.services.backtest_data_service as backtest_data_service
import backtesting.services.leaderboard_service as leaderboard_service
import backtesting.services.report_service as report_service
import backtesting.services.simulation_service as simulation_service
from backtesting.models.report import (
    BacktestFullReport,
    BacktestReportSnapshot,
    BacktestReportSummary,
    BacktestReportTrade,
)
from tests.support.backtesting import create_backtest_account, make_backtest_config, stub_market_data_provider


class TestBacktestRunFlow:
    def test_run_backtest_persists_isolated_results(self, conn, bt_market_data) -> None:
        create_backtest_account(conn, "acct_bt")
        bt_market_data(["AAPL", "MSFT"], [100.0, 103.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_bt", run_name="smoke"),
            provider=stub_market_data_provider(),
        )

        assert result.run_id > 0
        assert result.trade_count > 0

        row = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE id = ?", (result.run_id,)).fetchone()
        assert row is not None and int(row["n"]) == 1

        snapshots = conn.execute(
            "SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert snapshots is not None and int(snapshots["n"]) >= 2

        # Backtests must not touch live execution history (fills, revision 0006).
        live_fills = conn.execute("SELECT COUNT(*) AS n FROM order_fills").fetchone()
        assert live_fills is not None and int(live_fills["n"]) == 0

    def test_run_backtest_leaps_adds_financial_risk_warnings(self, conn, bt_market_data) -> None:
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
        bt_market_data(["AAPL"], [100.0, 102.0])

        result_without_opt_in = composition.run_backtest(
            conn,
            make_backtest_config("acct_leaps_bt"),
            provider=stub_market_data_provider(),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result_without_opt_in.warnings)
        assert any(
            "LEAPs approximation opt-in was not enabled" in warning for warning in result_without_opt_in.warnings
        )

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_leaps_bt", run_name="approx-ok", allow_approximate_leaps=True),
            provider=stub_market_data_provider(),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result.warnings)
        assert not any("opt-in was not enabled" in warning for warning in result.warnings)

    def test_backtest_report_returns_summary(self, conn, bt_market_data) -> None:
        create_backtest_account(conn, "acct_report_bt")
        bt_market_data(["AAPL"])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_report_bt", slippage_bps=1.0, run_name="for-report"),
            provider=stub_market_data_provider(),
        )

        summary = report_service.fetch_report(conn, run_id=result.run_id).to_payload()
        assert summary["run_id"] == result.run_id
        assert summary["account_name"] == "acct_report_bt"
        assert summary["trade_count"] >= 0
        assert isinstance(summary["total_return_pct"], float)

    def test_run_backtest_uses_account_trade_size_pct(self, conn, bt_market_data) -> None:
        create_backtest_account(conn, "acct_bt_size_small", trade_size_pct=5.0, max_position_pct=10.0)
        create_backtest_account(conn, "acct_bt_size_large", trade_size_pct=15.0, max_position_pct=30.0)
        bt_market_data(["AAPL"])

        small = composition.run_backtest(
            conn, make_backtest_config("acct_bt_size_small", run_name="small"), provider=stub_market_data_provider()
        )
        large = composition.run_backtest(
            conn, make_backtest_config("acct_bt_size_large", run_name="large"), provider=stub_market_data_provider()
        )

        small_qty = float(
            conn.execute(
                "SELECT qty FROM backtest_executions WHERE run_id = ? AND side = 'buy' ORDER BY id ASC LIMIT 1",
                (small.run_id,),
            ).fetchone()["qty"]
        )
        large_qty = float(
            conn.execute(
                "SELECT qty FROM backtest_executions WHERE run_id = ? AND side = 'buy' ORDER BY id ASC LIMIT 1",
                (large.run_id,),
            ).fetchone()["qty"]
        )

        assert small_qty < large_qty

    def test_backtest_report_summary_returns_model(self, conn, bt_market_data) -> None:
        create_backtest_account(conn, "acct_report_model")
        bt_market_data(["AAPL"], [100.0, 104.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_report_model", run_name="for-report-model"),
            provider=stub_market_data_provider(),
        )

        summary = report_service.fetch_report_summary(conn, result.run_id)
        assert isinstance(summary, BacktestReportSummary)
        assert summary.run_id == result.run_id
        assert summary.account_name == "acct_report_model"

    def test_report_reads_the_benchmark_without_market_data(
        self,
        conn,
        bt_market_data,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reading a report must not reach for market data.

        The benchmark return is frozen onto the run when it executes (revision
        0030), so the read is pure SQL. Before that it was recomputed here, which
        needed a provider injected at the seam and silently produced nothing
        wherever one was not — the leaderboard's case.
        """
        create_backtest_account(conn, "acct_report_provider_seam")
        bt_market_data(["AAPL"], [100.0, 104.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_report_provider_seam", run_name="for-provider-seam"),
            provider=stub_market_data_provider(),
        )

        def _fail(*_args, **_kwargs):
            raise AssertionError("reading a report must not fetch market data")

        monkeypatch.setattr(backtest_data_service, "fetch_benchmark_close", _fail)
        monkeypatch.setattr(backtest_data_service, "fetch_bar_history", _fail)

        report = report_service.fetch_report(conn, run_id=result.run_id)

        assert report.benchmark_return_pct == pytest.approx(result.benchmark_return_pct)
        assert report.alpha_pct == pytest.approx(report.summary.total_return_pct - report.benchmark_return_pct)

    def test_report_returns_typed_model_and_payload(self, conn, bt_market_data) -> None:
        create_backtest_account(conn, "acct_report_full")
        bt_market_data(["AAPL"], [100.0, 104.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_report_full", run_name="for-report-full"),
            provider=stub_market_data_provider(),
        )

        report = report_service.fetch_report(conn, run_id=result.run_id)
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
        assert payload["run_id"] == result.run_id
        assert payload["benchmark_ticker"] == "SPY"

    def test_backtest_report_and_leaderboard_use_run_strategy_snapshot(
        self,
        conn,
        bt_market_data,
    ) -> None:
        create_backtest_account(conn, "acct_strategy_snapshot")
        bt_market_data(["AAPL"], [100.0, 104.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config("acct_strategy_snapshot", slippage_bps=1.0, run_name="strategy-snapshot"),
            provider=stub_market_data_provider(),
        )

        from trading.services.accounts import set_account_strategy

        set_account_strategy(conn, "acct_strategy_snapshot", "mean_reversion")

        # The report reflects the run's own strategy (a strategies FK snapshot),
        # not the account's later strategy. The catalog stores the canonical key,
        # so the alias "trend_v1" surfaces as "trend" — still independent of the
        # account now being "mean_reversion".
        summary = report_service.fetch_report(conn, run_id=result.run_id).to_payload()
        assert summary["strategy"] == "trend"

        filtered = leaderboard_service.fetch_leaderboard(conn, limit=10, strategy="trend")
        assert any(entry.run_id == result.run_id for entry in filtered)

    def test_run_backtest_uses_strategy_signal_resolver(
        self, conn, monkeypatch: pytest.MonkeyPatch, bt_market_data
    ) -> None:
        create_backtest_account(conn, "acct_sig", strategy="macd_trend")

        call_count = {"n": 0}

        def fake_signal(
            _strategy_name: str,
            _history: pd.Series,
            _params: dict[str, object],
            _feature_history: pd.DataFrame | None = None,
        ) -> str:
            call_count["n"] += 1
            return "hold"

        bt_market_data(["AAPL"], [100.0, 101.0])
        monkeypatch.setattr(simulation_service, "evaluate_signal", fake_signal)

        composition.run_backtest(
            conn,
            make_backtest_config("acct_sig", run_name="sig-resolver"),
            provider=stub_market_data_provider(),
        )

        assert call_count["n"] > 0

    def test_run_backtest_monthly_universe_reconstitution_adds_warning(
        self,
        conn,
        tmp_path: Path,
        bt_market_data,
    ) -> None:
        create_backtest_account(conn, "acct_universe")

        history_dir = tmp_path / "universe_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "2026-01.txt").write_text("AAPL\n", encoding="utf-8")

        bt_market_data(["AAPL", "MSFT"], [100.0, 101.0])

        result = composition.run_backtest(
            conn,
            make_backtest_config(
                "acct_universe",
                universe_history_dir=str(history_dir),
                run_name="universe-reconstitution",
            ),
            provider=stub_market_data_provider(),
        )

        assert any("Monthly universe reconstitution enabled" in warning for warning in result.warnings)
        assert any("Universe snapshot missing" in warning for warning in result.warnings)
