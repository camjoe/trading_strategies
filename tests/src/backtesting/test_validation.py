import pandas as pd
import pytest

import backtesting.backtest as backtest_module
from tests.support.backtesting import bars_from_closes, create_backtest_account, make_backtest_config
from tests.support.strategies import ensure_strategy_id_for_label


class TestBacktestValidationAndFailurePaths:
    def test_run_backtest_rejects_unknown_account_strategy(self, conn, bt_market_data) -> None:
        # The backtest runs the default-book assignment's strategy (ADR 014);
        # an assignment carrying an unknown label must be rejected.
        from trading.services.books.book_assignments import sync_default_book_assignment

        create_backtest_account(conn, "acct_invalid_strategy")
        account_id = int(
            conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_invalid_strategy",)).fetchone()["id"]
        )
        sync_default_book_assignment(
            conn,
            account_id=account_id,
            strategy_name="mystery_strategy",
            now_iso="2026-01-01T00:00:00Z",
        )
        bt_market_data(["AAPL"], [100.0, 101.0])

        with pytest.raises(ValueError, match="Unknown strategy 'mystery_strategy'"):
            backtest_module.run_backtest(conn, make_backtest_config("acct_invalid_strategy"))

    def test_run_backtest_rejects_too_short_close_history(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_backtest_account(conn, "acct_short")

        short_idx = pd.date_range("2026-01-01", periods=2, freq="B")
        monkeypatch.setattr(backtest_module, "load_tickers_from_file", lambda _path: ["AAPL"])
        monkeypatch.setattr(
            backtest_module,
            "fetch_bar_history",
            lambda _tickers, _start, _end, **_kwargs: bars_from_closes(
                pd.DataFrame({"AAPL": [100.0, 101.0]}, index=short_idx)
            ),
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
                account_id, strategy_id, run_name, start_date, end_date, created_at,
                slippage_bps, fee_per_trade, tickers_file, notes, warnings
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(account_id),
                ensure_strategy_id_for_label(conn, "trend_v1"),
                "no-snapshots",
                "2026-01-01",
                "2026-02-01",
                "2026-03-27T00:00:00Z",
                0.0,
                0.0,
                "src/infrastructure/config/trade_universes/default.txt",
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

    def test_backtest_leaderboard_reports_the_benchmark_frozen_on_each_run(
        self,
        conn,
        bt_market_data,
    ) -> None:
        """The leaderboard's benchmark and alpha come from the run rows.

        They used to be recomputed per row against a ``fetch_benchmark_close``
        call that was given no provider, so ``require_provider`` raised, a broad
        ``except`` swallowed it, and both columns were empty on every row.
        """
        create_backtest_account(conn, "acct_lb_bench")
        bt_market_data(["AAPL"], [100.0, 101.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_bench", run_name="lb-benchmark"),
        )

        leaderboard = backtest_module.backtest_leaderboard(conn, limit=5, account_name="acct_lb_bench")

        assert len(leaderboard) == 1
        assert leaderboard[0]["benchmark_return_pct"] == pytest.approx(result.benchmark_return_pct)
        assert leaderboard[0]["alpha_pct"] == pytest.approx(
            leaderboard[0]["total_return_pct"] - leaderboard[0]["benchmark_return_pct"]
        )

    def test_backtest_leaderboard_reports_no_alpha_when_a_run_stored_no_benchmark(
        self,
        conn,
        bt_market_data,
    ) -> None:
        create_backtest_account(conn, "acct_lb_nobench")
        bt_market_data(["AAPL"], [100.0, 101.0])

        result = backtest_module.run_backtest(
            conn,
            make_backtest_config("acct_lb_nobench", run_name="lb-no-benchmark"),
        )
        conn.execute("UPDATE backtest_runs SET benchmark_return_pct = NULL WHERE id = ?", (result.run_id,))
        conn.commit()

        leaderboard = backtest_module.backtest_leaderboard(conn, limit=5, account_name="acct_lb_nobench")

        assert len(leaderboard) == 1
        assert leaderboard[0]["benchmark_return_pct"] is None
        assert leaderboard[0]["alpha_pct"] is None

    def test_run_backtest_batch_requires_non_empty_account_names(self, conn) -> None:
        with pytest.raises(ValueError, match="At least one account name is required"):
            backtest_module.run_backtest_batch(
                conn,
                backtest_module.BacktestBatchConfig(
                    account_names=["  ", ""],
                    tickers_file="src/infrastructure/config/trade_universes/default.txt",
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
