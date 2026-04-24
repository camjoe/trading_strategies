import pandas as pd
import pytest

import trading.backtesting.backtest as backtest_module
from tests.support import (
    create_backtest_account,
    install_backtest_market_data,
    make_backtest_config,
    make_fake_close_history,
    make_walk_forward_config,
)


class TestBacktestWalkForwardAndWarnings:
    def test_run_walk_forward_backtest_creates_multiple_runs(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_wf")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        summary = backtest_module.run_walk_forward_backtest(
            conn,
            make_walk_forward_config(
                "acct_wf",
                start="2026-01-01",
                end="2026-03-31",
                test_months=1,
                step_months=1,
                run_name_prefix="wf-test",
            ),
        )

        assert summary.window_count == 3
        assert len(summary.run_ids) == 3

        rows = conn.execute("SELECT COUNT(*) AS n FROM backtest_runs").fetchone()
        assert rows is not None and int(rows["n"]) == 3

    def test_preview_backtest_warnings_includes_leaps_and_research_only_warning(self, conn) -> None:
        create_backtest_account(
            conn,
            "acct_preview_leaps",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        warnings = backtest_module.preview_backtest_warnings(
            conn,
            make_backtest_config("acct_preview_leaps", slippage_bps=0.0),
        )

        assert any("LEAPs mode is approximated" in warning for warning in warnings)
        assert any("opt-in was not enabled" in warning for warning in warnings)
        assert any("daily close data only" in warning for warning in warnings)

    def test_backtest_report_persists_warning_string(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(
            conn,
            "acct_report_warn",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        monkeypatch.setattr(backtest_module, "load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(backtest_module, "fetch_close_history", lambda _tickers, _start, _end: make_fake_close_history(_tickers))
        monkeypatch.setattr(
            backtest_module,
            "fetch_benchmark_close",
            lambda _ticker, _start, _end: pd.Series(
                [100.0, 102.0],
                index=pd.date_range("2026-01-01", periods=2, freq="B"),
            ),
        )

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_report_warn", run_name="warn-report"),
        )

        summary = backtest_module.backtest_report(conn, result.run_id)
        warnings = str(summary["warnings"])
        assert "LEAPs mode is approximated" in warnings
        assert "opt-in was not enabled" in warnings

    def test_run_walk_forward_backtest_no_generated_windows_raises(self, conn) -> None:
        create_backtest_account(conn, "acct_wf_empty")

        with pytest.raises(ValueError, match="No walk-forward windows generated"):
            backtest_module.run_walk_forward_backtest(
                conn,
                make_walk_forward_config(
                    "acct_wf_empty",
                    start="2026-01-31",
                    end="2026-02-01",
                    test_months=1,
                    step_months=2,
                    run_name_prefix="wf-empty",
                ),
            )
