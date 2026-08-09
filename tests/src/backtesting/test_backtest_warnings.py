import pandas as pd
import pytest

import backtesting.backtest as backtest_module
import backtesting.services.backtest_data_service as backtest_data_service
import backtesting.services.execution_service as execution_service
from tests.support.backtesting import (
    bars_from_closes,
    create_backtest_account,
    make_backtest_config,
    make_fake_close_history,
)


class TestBacktestWarnings:
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

        warnings = execution_service.preview_backtest_warnings(
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

        monkeypatch.setattr(backtest_data_service, "load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "fetch_bar_history",
            lambda _tickers, _start, _end, **_kwargs: bars_from_closes(make_fake_close_history(_tickers)),
        )
        monkeypatch.setattr(
            backtest_module,
            "fetch_benchmark_close",
            lambda _ticker, _start, _end, **_kwargs: pd.Series(
                [100.0, 102.0],
                index=pd.date_range("2026-01-01", periods=2, freq="B"),
            ),
        )

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_report_warn", run_name="warn-report"),
        )

        summary = backtest_module.backtest_report_full(conn, result.run_id).to_payload()
        warnings = str(summary["warnings"])
        assert "LEAPs mode is approximated" in warnings
        assert "opt-in was not enabled" in warnings
