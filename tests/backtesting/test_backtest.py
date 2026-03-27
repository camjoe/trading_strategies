from __future__ import annotations

from pathlib import Path
from datetime import date

import pandas as pd
import pytest

from trading.accounts import create_account
from common.market_data import FeatureBundle, ProxyFeatureDataProvider
from trading.backtesting.backtest import (
    BacktestBatchConfig,
    BacktestConfig,
    BacktestResult,
    WalkForwardConfig,
    _add_months,
    _benchmark_return_pct,
    _compute_market_value,
    _compute_unrealized_pnl,
    _max_drawdown_pct,
    _normalize_benchmark_series,
    backtest_leaderboard,
    backtest_report,
    build_walk_forward_windows,
    preview_backtest_warnings,
    run_backtest,
    run_backtest_batch,
    run_walk_forward_backtest,
)


def _fake_close_history(tickers: list[str]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=40, freq="B")
    data: dict[str, list[float]] = {}
    for i, ticker in enumerate(tickers):
        base = 100.0 + (i * 5.0)
        # Uptrend then mild pullback to force both buy and sell decisions.
        values = [base + (j * 0.8) for j in range(30)] + [base + 24.0 - ((j - 30) * 0.9) for j in range(30, 40)]
        data[ticker] = values
    return pd.DataFrame(data, index=idx)


def _patch_market_data(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tickers: list[str],
    benchmark_values: list[float],
) -> None:
    monkeypatch.setattr("trading.backtesting.backtest.load_tickers_from_file", lambda _path: tickers)
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_close_history",
        lambda _tickers, _start, _end: _fake_close_history(_tickers),
    )
    monkeypatch.setattr(
        "trading.backtesting.backtest.fetch_benchmark_close",
        lambda _ticker, _start, _end: pd.Series(
            benchmark_values,
            index=pd.date_range("2026-01-01", periods=len(benchmark_values), freq="B"),
        ),
    )


def _create_bt_account(
    conn,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 10000.0,
    benchmark: str = "SPY",
    **kwargs,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, **kwargs)


def _backtest_config(
    account_name: str,
    *,
    start: str = "2026-01-01",
    end: str = "2026-03-01",
    universe_history_dir: str | None = None,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    run_name: str | None = None,
    allow_approximate_leaps: bool = False,
) -> BacktestConfig:
    return BacktestConfig(
        account_name=account_name,
        tickers_file="trading/trade_universe.txt",
        universe_history_dir=universe_history_dir,
        start=start,
        end=end,
        lookback_months=None,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
        run_name=run_name,
        allow_approximate_leaps=allow_approximate_leaps,
    )


def _walk_forward_config(
    account_name: str,
    *,
    start: str,
    end: str,
    test_months: int,
    step_months: int,
    slippage_bps: float = 5.0,
    fee_per_trade: float = 0.0,
    run_name_prefix: str | None = None,
    allow_approximate_leaps: bool = False,
) -> WalkForwardConfig:
    return WalkForwardConfig(
        account_name=account_name,
        tickers_file="trading/trade_universe.txt",
        universe_history_dir=None,
        start=start,
        end=end,
        lookback_months=None,
        test_months=test_months,
        step_months=step_months,
        slippage_bps=slippage_bps,
        fee_per_trade=fee_per_trade,
        run_name_prefix=run_name_prefix,
        allow_approximate_leaps=allow_approximate_leaps,
    )


class TestBacktestRunFlow:
    def test_run_backtest_persists_isolated_results(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(conn, "acct_bt")
        _patch_market_data(monkeypatch, tickers=["AAPL", "MSFT"], benchmark_values=[100.0, 103.0])

        result = run_backtest(
            conn,
            _backtest_config("acct_bt", run_name="smoke"),
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
        _create_bt_account(
            conn,
            "acct_leaps_bt",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 102.0])

        result_without_opt_in = run_backtest(
            conn,
            _backtest_config("acct_leaps_bt"),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result_without_opt_in.warnings)
        assert any("LEAPs approximation opt-in was not enabled" in warning for warning in result_without_opt_in.warnings)

        result = run_backtest(
            conn,
            _backtest_config("acct_leaps_bt", run_name="approx-ok", allow_approximate_leaps=True),
        )
        assert any("LEAPs mode is approximated" in warning for warning in result.warnings)
        assert not any("opt-in was not enabled" in warning for warning in result.warnings)

    def test_backtest_report_returns_summary(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(conn, "acct_report_bt")
        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 105.0])

        result = run_backtest(
            conn,
            _backtest_config("acct_report_bt", slippage_bps=1.0, run_name="for-report"),
        )

        summary = backtest_report(conn, result.run_id)
        assert summary["run_id"] == result.run_id
        assert summary["account_name"] == "acct_report_bt"
        assert summary["trade_count"] >= 0
        assert isinstance(summary["total_return_pct"], float)

    def test_backtest_report_and_leaderboard_use_run_strategy_snapshot(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_bt_account(conn, "acct_strategy_snapshot")
        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 104.0])

        result = run_backtest(
            conn,
            _backtest_config("acct_strategy_snapshot", slippage_bps=1.0, run_name="strategy-snapshot"),
        )

        conn.execute("UPDATE accounts SET strategy = ? WHERE name = ?", ("mean_reversion", "acct_strategy_snapshot"))
        conn.commit()

        summary = backtest_report(conn, result.run_id)
        assert summary["strategy"] == "trend_v1"

        filtered = backtest_leaderboard(conn, limit=10, strategy="trend_v1")
        assert any(row["run_id"] == result.run_id for row in filtered)

    def test_run_backtest_uses_strategy_signal_resolver(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(conn, "acct_sig", strategy="macd_trend")

        call_count = {"n": 0}

        def fake_signal(_strategy_name: str, _history: pd.Series) -> str:
            call_count["n"] += 1
            return "hold"

        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 101.0])
        monkeypatch.setattr("trading.backtesting.backtest.resolve_signal", fake_signal)

        run_backtest(
            conn,
            _backtest_config("acct_sig", run_name="sig-resolver"),
        )

        assert call_count["n"] > 0

    def test_run_backtest_monthly_universe_reconstitution_adds_warning(
        self,
        conn,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_bt_account(conn, "acct_universe")

        history_dir = tmp_path / "universe_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "2026-01.txt").write_text("AAPL\n", encoding="utf-8")

        _patch_market_data(monkeypatch, tickers=["AAPL", "MSFT"], benchmark_values=[100.0, 101.0])

        result = run_backtest(
            conn,
            _backtest_config(
                "acct_universe",
                universe_history_dir=str(history_dir),
                run_name="universe-reconstitution",
            ),
        )

        assert any("Monthly universe reconstitution enabled" in warning for warning in result.warnings)
        assert any("Universe snapshot missing" in warning for warning in result.warnings)


class TestBacktestProxyFeatureFlow:
    def test_proxy_feature_provider_builds_aligned_topic_features(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        idx = pd.date_range("2026-01-01", periods=40, freq="B")
        close_history = pd.DataFrame(
            {
                "AAPL": [100.0 + i for i in range(40)],
                "XOM": [80.0 + (i * 0.5) for i in range(40)],
            },
            index=idx,
        )

        category_file = tmp_path / "ticker_categories.txt"
        category_file.write_text("[tech]\nAAPL\n[energy]\nXOM\n", encoding="utf-8")

        proxy_index = pd.date_range("2025-11-01", periods=90, freq="B")
        proxy_frame = pd.DataFrame(
            {
                "SPY": [100.0 + (i * 0.2) for i in range(90)],
                "XLK": [100.0 + (i * 0.35) for i in range(90)],
                "XLE": [100.0 + (i * 0.25) for i in range(90)],
                "TLT": [100.0 + (i * 0.05) for i in range(90)],
                "^VIX": [20.0 + ((i % 5) * 0.1) for i in range(90)],
            },
            index=proxy_index,
        )

        class StubProvider:
            def fetch_close_history(self, tickers: list[str], _start, _end) -> pd.DataFrame:
                return proxy_frame.loc[:, tickers]

        monkeypatch.setattr("common.market_data.get_provider", lambda: StubProvider())

        provider = ProxyFeatureDataProvider(category_file=str(category_file))
        bundle = provider.build_feature_bundle(["AAPL", "XOM"], date(2026, 1, 1), date(2026, 3, 1), close_history)

        aapl_features = bundle.history_for_ticker("AAPL", idx[-1])
        assert aapl_features is not None
        assert "topic_proxy_rel_strength" in aapl_features.columns
        assert float(aapl_features["topic_proxy_available"].iloc[-1]) == 1.0
        assert pd.notna(aapl_features["macro_risk_on_score"].iloc[-1])

    def test_run_backtest_passes_feature_history_for_proxy_strategies(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_bt_account(conn, "acct_topic", strategy="topic_proxy_rotation")
        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        idx = pd.date_range("2026-01-01", periods=40, freq="B")
        feature_frame = pd.DataFrame(
            {
                "topic_proxy_available": [1.0] * 40,
                "topic_proxy_rel_strength": [0.02] * 40,
                "topic_proxy_trend_gap": [0.01] * 40,
            },
            index=idx,
        )

        class StubFeatureProvider:
            def build_feature_bundle(self, _tickers, _start, _end, _close_history) -> FeatureBundle:
                return FeatureBundle(ticker_features={"AAPL": feature_frame})

        call_count = {"n": 0}

        def fake_signal(_strategy_name: str, _history: pd.Series, feature_history: pd.DataFrame | None = None) -> str:
            call_count["n"] += 1
            assert feature_history is not None
            assert "topic_proxy_rel_strength" in feature_history.columns
            return "hold"

        monkeypatch.setattr("trading.backtesting.backtest.get_feature_provider", lambda: StubFeatureProvider())
        monkeypatch.setattr("trading.backtesting.backtest.resolve_signal", fake_signal)

        run_backtest(
            conn,
            _backtest_config("acct_topic", run_name="topic-proxy"),
        )

        assert call_count["n"] > 0


class TestBacktestWalkForwardAndWarnings:
    def test_build_walk_forward_windows_monthly_rolls(self) -> None:
        windows = build_walk_forward_windows(
            start_date=date(2026, 1, 15),
            end_date=date(2026, 4, 10),
            test_months=1,
            step_months=1,
        )

        assert windows == [
            (date(2026, 1, 15), date(2026, 1, 31)),
            (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 3, 1), date(2026, 3, 31)),
            (date(2026, 4, 1), date(2026, 4, 10)),
        ]

    def test_run_walk_forward_backtest_creates_multiple_runs(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(conn, "acct_wf")
        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        summary = run_walk_forward_backtest(
            conn,
            _walk_forward_config(
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
        _create_bt_account(
            conn,
            "acct_preview_leaps",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        warnings = preview_backtest_warnings(
            conn,
            _backtest_config("acct_preview_leaps", slippage_bps=0.0),
        )

        assert any("LEAPs mode is approximated" in warning for warning in warnings)
        assert any("opt-in was not enabled" in warning for warning in warnings)
        assert any("daily close data only" in warning for warning in warnings)

    def test_backtest_report_persists_warning_string(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(
            conn,
            "acct_report_warn",
            initial_cash=5000.0,
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        monkeypatch.setattr("trading.backtesting.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(
            "trading.backtesting.backtest.fetch_close_history",
            lambda _tickers, _start, _end: _fake_close_history(_tickers),
        )
        monkeypatch.setattr(
            "trading.backtesting.backtest.fetch_benchmark_close",
            lambda _ticker, _start, _end: pd.Series(
                [100.0, 102.0],
                index=pd.date_range("2026-01-01", periods=2, freq="B"),
            ),
        )

        result = run_backtest(
            conn,
            _backtest_config("acct_report_warn", run_name="warn-report"),
        )

        summary = backtest_report(conn, result.run_id)
        warnings = str(summary["warnings"])
        assert "LEAPs mode is approximated" in warnings
        assert "opt-in was not enabled" in warnings

    def test_build_walk_forward_windows_rejects_non_positive_lengths(self) -> None:
        with pytest.raises(ValueError, match="test_months must be > 0"):
            build_walk_forward_windows(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 1),
                test_months=0,
                step_months=1,
            )

        with pytest.raises(ValueError, match="step_months must be > 0"):
            build_walk_forward_windows(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 1),
                test_months=1,
                step_months=0,
            )

    def test_run_walk_forward_backtest_no_generated_windows_raises(self, conn) -> None:
        _create_bt_account(conn, "acct_wf_empty")

        with pytest.raises(ValueError, match="No walk-forward windows generated"):
            run_walk_forward_backtest(
                conn,
                _walk_forward_config(
                    "acct_wf_empty",
                    start="2026-01-31",
                    end="2026-02-01",
                    test_months=1,
                    step_months=2,
                    run_name_prefix="wf-empty",
                ),
            )


class TestBacktestLeaderboardAndBatch:
    def test_backtest_leaderboard_sorts_by_total_return_and_supports_filters(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_bt_account(conn, "acct_lb_trend")
        _create_bt_account(conn, "acct_lb_mean", strategy="mean_reversion")

        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        run_backtest(
            conn,
            _backtest_config("acct_lb_trend", run_name="lb-trend"),
        )
        run_backtest(
            conn,
            _backtest_config("acct_lb_mean", run_name="lb-mean"),
        )

        leaderboard = backtest_leaderboard(conn, limit=10)
        assert len(leaderboard) >= 2
        assert leaderboard[0]["total_return_pct"] >= leaderboard[1]["total_return_pct"]
        assert "max_drawdown_pct" in leaderboard[0]
        assert "benchmark_return_pct" in leaderboard[0]
        assert "alpha_pct" in leaderboard[0]

        filtered = backtest_leaderboard(conn, limit=10, strategy="mean")
        assert len(filtered) == 1
        assert filtered[0]["account_name"] == "acct_lb_mean"

    def test_run_backtest_batch_sorts_results_and_applies_run_name_prefix(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        results_map = {
            "acct_a": BacktestResult(
                run_id=1,
                account_name="acct_a",
                start_date="2026-01-01",
                end_date="2026-02-01",
                tickers=["AAPL"],
                trade_count=1,
                ending_equity=10100.0,
                total_return_pct=1.0,
                benchmark_return_pct=0.5,
                alpha_pct=0.5,
                max_drawdown_pct=-1.0,
                warnings=[],
            ),
            "acct_b": BacktestResult(
                run_id=2,
                account_name="acct_b",
                start_date="2026-01-01",
                end_date="2026-02-01",
                tickers=["AAPL"],
                trade_count=2,
                ending_equity=10800.0,
                total_return_pct=8.0,
                benchmark_return_pct=0.5,
                alpha_pct=7.5,
                max_drawdown_pct=-2.0,
                warnings=[],
            ),
        }

        seen_run_names: list[str | None] = []

        def _fake_run_backtest(_conn, cfg: BacktestConfig) -> BacktestResult:
            seen_run_names.append(cfg.run_name)
            return results_map[cfg.account_name]

        monkeypatch.setattr("trading.backtesting.backtest.run_backtest", _fake_run_backtest)

        results = run_backtest_batch(
            conn,
            BacktestBatchConfig(
                account_names=["acct_a", "acct_b"],
                tickers_file="trading/trade_universe.txt",
                universe_history_dir=None,
                start="2026-01-01",
                end="2026-02-01",
                lookback_months=None,
                slippage_bps=5.0,
                fee_per_trade=0.0,
                run_name_prefix="batch",
                allow_approximate_leaps=False,
            ),
        )

        assert [item.account_name for item in results] == ["acct_b", "acct_a"]
        assert seen_run_names == ["batch_01_acct_a", "batch_02_acct_b"]


class TestBacktestInternalHelpers:
    def test_build_walk_forward_windows_rejects_start_after_end(self) -> None:
        with pytest.raises(ValueError, match="start_date must be before end_date"):
            build_walk_forward_windows(
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 1),
                test_months=1,
                step_months=1,
            )

    def test_add_months_clips_end_of_month_and_rejects_negative(self) -> None:
        assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
        assert _add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

        with pytest.raises(ValueError, match="months must be >= 0"):
            _add_months(date(2026, 1, 1), -1)

    def test_market_value_and_unrealized_pnl_ignore_missing_or_non_positive_positions(self) -> None:
        positions = {"AAPL": 2.0, "MSFT": 1.5, "NVDA": 0.0}
        prices = {"AAPL": 10.0, "MSFT": 20.0}
        avg_cost = {"AAPL": 8.0, "MSFT": 25.0, "NVDA": 100.0}

        assert _compute_market_value(positions, prices) == pytest.approx(50.0)
        assert _compute_unrealized_pnl(positions, avg_cost, prices) == pytest.approx(-3.5)

    def test_max_drawdown_handles_empty_and_non_positive_peak(self) -> None:
        assert _max_drawdown_pct([]) == 0.0
        assert _max_drawdown_pct([0.0, -10.0, -5.0]) == 0.0
        assert _max_drawdown_pct([100.0, 90.0, 95.0, 80.0]) == pytest.approx(-20.0)

    def test_normalize_benchmark_series_accepts_series_and_dataframe(self) -> None:
        series = pd.Series([100.0, "bad", None, 101.0])
        normalized_series = _normalize_benchmark_series(series)
        assert list(normalized_series.values) == [100.0, 101.0]

        frame = pd.DataFrame({"SPY": [100.0, "bad", 102.0]})
        normalized_frame = _normalize_benchmark_series(frame)
        assert list(normalized_frame.values) == [100.0, 102.0]

    def test_benchmark_return_pct_edge_cases(self) -> None:
        assert _benchmark_return_pct(pd.Series([100.0]), initial_cash=10000.0) is None
        assert _benchmark_return_pct(pd.Series([0.0, 110.0]), initial_cash=10000.0) is None
        assert _benchmark_return_pct(pd.Series([100.0, 110.0]), initial_cash=10000.0) == pytest.approx(10.0)


class TestBacktestValidationAndFailurePaths:
    def test_run_backtest_rejects_too_short_close_history(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_bt_account(conn, "acct_short")

        short_idx = pd.date_range("2026-01-01", periods=2, freq="B")
        monkeypatch.setattr("trading.backtesting.backtest.load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(
            "trading.backtesting.backtest.fetch_close_history",
            lambda _tickers, _start, _end: pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_idx),
        )

        with pytest.raises(ValueError, match="Need at least 3 trading days"):
            run_backtest(conn, _backtest_config("acct_short"))

    def test_backtest_report_missing_run_raises(self, conn) -> None:
        with pytest.raises(ValueError, match="Backtest run id 9999 not found"):
            backtest_report(conn, 9999)

    def test_backtest_report_raises_when_snapshots_missing(self, conn) -> None:
        _create_bt_account(conn, "acct_no_snap")
        account_id = conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_no_snap",)).fetchone()["id"]
        cursor = conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id, strategy_name, run_name, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                "trend_v1",
                "no-snapshots",
                "2026-01-01",
                "2026-02-01",
                "2026-03-27T00:00:00Z",
                0.0,
                0.0,
                "trading/trade_universe.txt",
                "test",
                "",
            ),
        )
        conn.commit()
        run_id = int(cursor.lastrowid)

        with pytest.raises(ValueError, match="No snapshots found"):
            backtest_report(conn, run_id)

    def test_backtest_leaderboard_rejects_non_positive_limit(self, conn) -> None:
        with pytest.raises(ValueError, match="limit must be > 0"):
            backtest_leaderboard(conn, limit=0)

    def test_backtest_leaderboard_gracefully_handles_benchmark_fetch_error(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _create_bt_account(conn, "acct_lb_bench")
        _patch_market_data(monkeypatch, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        run_backtest(
            conn,
            _backtest_config("acct_lb_bench", run_name="lb-benchmark-error"),
        )
        monkeypatch.setattr(
            "trading.backtesting.backtest.fetch_benchmark_close",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
        )

        leaderboard = backtest_leaderboard(conn, limit=5, account_name="acct_lb_bench")

        assert len(leaderboard) == 1
        assert leaderboard[0]["benchmark_return_pct"] is None
        assert leaderboard[0]["alpha_pct"] is None

    def test_run_backtest_batch_requires_non_empty_account_names(self, conn) -> None:
        with pytest.raises(ValueError, match="At least one account name is required"):
            run_backtest_batch(
                conn,
                BacktestBatchConfig(
                    account_names=["  ", ""],
                    tickers_file="trading/trade_universe.txt",
                    universe_history_dir=None,
                    start="2026-01-01",
                    end="2026-02-01",
                    lookback_months=None,
                    slippage_bps=0.0,
                    fee_per_trade=0.0,
                    run_name_prefix=None,
                    allow_approximate_leaps=False,
                ),
            )
