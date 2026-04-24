import pandas as pd
import pytest

import trading.backtesting.backtest as backtest_module
import trading.backtesting.services.leaderboard_service as leaderboard_service
from tests.support.backtesting import (
    create_backtest_account,
    install_backtest_market_data,
    make_backtest_config,
)


class TestBacktestValidationAndFailurePaths:
    def test_run_backtest_rejects_unknown_account_strategy(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_invalid_strategy")
        conn.execute("UPDATE accounts SET strategy = ? WHERE name = ?", ("mystery_strategy", "acct_invalid_strategy"))
        conn.commit()
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_invalid_strategy"))

    def test_run_backtest_rejects_too_short_close_history(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_short")

        short_idx = pd.date_range("2026-01-01", periods=2, freq="B")
        monkeypatch.setattr(backtest_module, "load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "fetch_close_history",
            lambda _tickers, _start, _end: pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_idx),
        )

        with pytest.raises(ValueError, match="Need at least 3 trading days"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_short"))

    def test_backtest_report_missing_run_raises(self, conn) -> None:
        with pytest.raises(ValueError, match="Backtest run id 9999 not found"):
            backtest_module.backtest_report(conn, 9999)

    def test_backtest_report_raises_when_snapshots_missing(self, conn) -> None:
        create_backtest_account(conn, "acct_no_snap")
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
                "trading/config/trade_universe.txt",
                "test",
                "",
            ),
        )
        conn.commit()
        run_id = int(cursor.lastrowid)

        with pytest.raises(ValueError, match="No snapshots found"):
            backtest_module.backtest_report(conn, run_id)

    def test_backtest_leaderboard_rejects_non_positive_limit(self, conn) -> None:
        with pytest.raises(ValueError, match="limit must be > 0"):
            backtest_module.backtest_leaderboard(conn, limit=0)

    def test_backtest_leaderboard_rejects_unknown_strategy_filter(self, conn) -> None:
        with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
            backtest_module.backtest_leaderboard(conn, limit=5, strategy="mystery_strategy")

    def test_backtest_leaderboard_gracefully_handles_benchmark_fetch_error(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        create_backtest_account(conn, "acct_lb_bench")
        install_backtest_market_data(monkeypatch, backtest_module, tickers=["AAPL"], benchmark_values=[100.0, 101.0])

        backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_bench", run_name="lb-benchmark-error"),
        )
        monkeypatch.setattr(
            leaderboard_service,
            "fetch_benchmark_close",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("boom")),
        )

        leaderboard = backtest_module.backtest_leaderboard(conn, limit=5, account_name="acct_lb_bench")

        assert len(leaderboard) == 1
        assert leaderboard[0]["benchmark_return_pct"] is None
        assert leaderboard[0]["alpha_pct"] is None

    def test_run_backtest_batch_requires_non_empty_account_names(self, conn) -> None:
        with pytest.raises(ValueError, match="At least one account name is required"):
            backtest_module.run_backtest_batch(
                conn,
                backtest_module.BacktestBatchConfig(
                    account_names=["  ", ""],
                    tickers_file="trading/config/trade_universe.txt",
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
