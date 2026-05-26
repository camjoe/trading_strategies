import pytest

import trading.backtesting.backtest as backtest_module
from trading.backtesting.models import BacktestBatchConfig
from trading.backtesting.report_models import BacktestLeaderboardEntry
from tests.support.backtesting import create_backtest_account, make_backtest_config, make_backtest_result


class TestBacktestLeaderboardAndBatch:
    def test_backtest_leaderboard_sorts_by_total_return_and_supports_filters(
        self,
        conn,
        bt_market_data,
    ) -> None:
        create_backtest_account(conn, "acct_lb_trend")
        create_backtest_account(conn, "acct_lb_mean", strategy="mean_reversion")

        bt_market_data(["AAPL"], [100.0, 101.0])

        backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_trend", run_name="lb-trend"),
        )
        backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_mean", run_name="lb-mean"),
        )

        leaderboard = backtest_module.backtest_leaderboard(conn, limit=10)
        assert len(leaderboard) >= 2
        assert leaderboard[0]["total_return_pct"] >= leaderboard[1]["total_return_pct"]
        assert "max_drawdown_pct" in leaderboard[0]
        assert "benchmark_return_pct" in leaderboard[0]
        assert "alpha_pct" in leaderboard[0]
        assert "sharpe_ratio" in leaderboard[0]
        assert "profit_factor" in leaderboard[0]

        filtered = backtest_module.backtest_leaderboard(conn, limit=10, strategy="mean")
        assert len(filtered) == 1
        assert filtered[0]["account_name"] == "acct_lb_mean"

    def test_backtest_leaderboard_entries_returns_models(
        self,
        conn,
        bt_market_data,
    ) -> None:
        create_backtest_account(conn, "acct_lb_entries")
        bt_market_data(["AAPL"], [100.0, 101.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_entries", run_name="lb-entries"),
        )

        entries = backtest_module.backtest_leaderboard_entries(conn, limit=5, account_name="acct_lb_entries")
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, BacktestLeaderboardEntry)
        assert entry.run_id == result.run_id
        assert entry.account_name == "acct_lb_entries"

    def test_run_backtest_batch_sorts_results_and_applies_run_name_prefix(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        results_map = {
            "acct_a": make_backtest_result(
                "acct_a", run_id=1, total_return_pct=1.0, ending_equity=10_100.0, trade_count=1
            ),
            "acct_b": make_backtest_result(
                "acct_b", run_id=2, total_return_pct=8.0, ending_equity=10_800.0, trade_count=2
            ),
        }

        seen_run_names: list[str | None] = []

        def _fake_run_backtest(_conn, cfg):
            seen_run_names.append(cfg.run_name)
            return results_map[cfg.account_name]

        monkeypatch.setattr(backtest_module, "run_backtest", _fake_run_backtest)

        results = backtest_module.run_backtest_batch(
            conn,
            BacktestBatchConfig(
                account_names=["acct_a", "acct_b"],
                tickers_file="trading/config/trade_universe.txt",
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
