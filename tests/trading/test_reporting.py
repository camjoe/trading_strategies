import pytest

from trading.services.accounts_service import create_account, get_account
import trading.services.reporting_service as reporting_service
from trading.models import AccountConfig
from trading.services.reporting_service import (
    account_report,
    build_account_stats,
    compare_strategies,
    format_goal_text,
    infer_overall_trend,
    show_snapshots,
    snapshot_account,
)


def _insert_trade(
    conn,
    account_id: int,
    ticker: str,
    qty: float,
    price: float,
    trade_time: str = "2026-01-01T00:00:00Z",
) -> None:
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, ticker, "buy", qty, price, 0.0, trade_time, "entry"),
    )


def _insert_snapshot(conn, account_id: int, snapshot_time: str, equity: float) -> None:
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, snapshot_time, equity, 0.0, equity, 0.0, 0.0),
    )


class TestBuildAccountStats:
    def test_uses_price_map(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_account(conn, "acct_report", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_report")

        _insert_trade(conn, account["id"], "AAPL", 2.0, 100.0)
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {"AAPL": 120.0})

        state, prices, market_value, unrealized, equity = build_account_stats(conn, account)

        assert state.cash == pytest.approx(800.0)
        assert prices == {"AAPL": 120.0}
        assert market_value == pytest.approx(240.0)
        assert unrealized == pytest.approx(40.0)
        assert equity == pytest.approx(1040.0)

    def test_ignores_positions_without_price(self, conn, monkeypatch: pytest.MonkeyPatch) -> None:
        create_account(conn, "acct_missing_px", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_missing_px")

        _insert_trade(conn, account["id"], "AAPL", 2.0, 100.0)
        _insert_trade(conn, account["id"], "MSFT", 1.0, 50.0, trade_time="2026-01-01T00:00:01Z")
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {"AAPL": 120.0})

        state, prices, market_value, unrealized, equity = build_account_stats(conn, account)

        assert state.cash == pytest.approx(750.0)
        assert prices == {"AAPL": 120.0}
        assert market_value == pytest.approx(240.0)
        assert unrealized == pytest.approx(40.0)
        assert equity == pytest.approx(990.0)


class TestTrendInference:
    def test_up(self, conn) -> None:
        create_account(conn, "acct_trend", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_trend")

        for i, equity in enumerate([980.0, 1000.0, 1015.0], start=1):
            _insert_snapshot(conn, account["id"], f"2026-01-0{i}T00:00:00Z", equity)
        conn.commit()

        trend = infer_overall_trend(conn, account["id"], current_equity=1030.0, lookback=10)
        assert trend == "up"

    def test_insufficient_data(self, conn) -> None:
        create_account(conn, "acct_short", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_short")

        trend = infer_overall_trend(conn, account["id"], current_equity=1000.0, lookback=10)
        assert trend == "insufficient-data"

    def test_down_and_flat(self, conn) -> None:
        create_account(conn, "acct_trend_df", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_trend_df")

        for i, equity in enumerate([1000.0, 995.0, 990.0], start=1):
            _insert_snapshot(conn, account["id"], f"2026-02-0{i}T00:00:00Z", equity)
        conn.commit()

        assert infer_overall_trend(conn, account["id"], current_equity=980.0, lookback=10) == "down"
        assert infer_overall_trend(conn, account["id"], current_equity=991.0, lookback=10) == "flat"

    def test_zero_first_equity_is_insufficient(self, conn) -> None:
        create_account(conn, "acct_zero", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_zero")

        _insert_snapshot(conn, account["id"], "2026-02-01T00:00:00Z", 0.0)
        _insert_snapshot(conn, account["id"], "2026-02-02T00:00:00Z", 10.0)
        conn.commit()

        trend = infer_overall_trend(conn, account["id"], current_equity=20.0, lookback=10)
        assert trend == "insufficient-data"


@pytest.mark.parametrize(
    ("goal_min", "goal_max", "goal_period", "expected"),
    [
        (None, None, "monthly", "not-set"),
        (1.5, 3.5, "weekly", "1.50% to 3.50% per weekly"),
        (2.0, None, "monthly", ">= 2.00% per monthly"),
        (None, 4.0, "quarterly", "<= 4.00% per quarterly"),
    ],
)
def test_format_goal_text_variants(conn, goal_min, goal_max, goal_period, expected: str) -> None:
    create_account(
        conn,
        "acct_goal",
        "Trend",
        1000.0,
        "SPY",
        config=AccountConfig(
            goal_min_return_pct=goal_min,
            goal_max_return_pct=goal_max,
            goal_period=goal_period,
        ),
    )
    account = get_account(conn, "acct_goal")
    assert format_goal_text(account) == expected


class TestAccountReportOutput:
    def test_with_and_without_benchmark(self, conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        create_account(conn, "acct_report_out", "Trend", 1000.0, "SPY")
        account = get_account(conn, "acct_report_out")

        _insert_trade(conn, account["id"], "AAPL", 2.0, 100.0)
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {"AAPL": 120.0})
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (1050.0, 5.0))

        stats, positions = account_report(conn, "acct_report_out")
        out = capsys.readouterr().out

        assert stats["equity"] == pytest.approx(1040.0)
        assert positions == {"AAPL": 2.0}
        assert "Display Name: acct_report_out" in out
        assert (
            "Account Policy: base_strategy=Trend | active_strategy=Trend | benchmark=SPY | "
            "heuristic_exploration=off | risk=none | instrument=equity"
        ) in out
        assert "Benchmark Equity: 1050.00" in out
        assert "Account Alpha vs Benchmark %: -1.00" in out
        assert "Open Positions:" in out

        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (None, None))
        account_report(conn, "acct_report_out")
        out2 = capsys.readouterr().out
        assert "Benchmark comparison: unavailable (price history not found)" in out2

    def test_prints_leaps_fields(self, conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        create_account(
            conn,
            "acct_leaps",
            "Trend",
            5000.0,
            "SPY",
            config=AccountConfig(
                instrument_mode="leaps",
                option_strike_offset_pct=5.0,
                option_min_dte=120,
                option_max_dte=365,
                option_type="call",
                target_delta_min=0.2,
                target_delta_max=0.4,
                iv_rank_min=20.0,
                iv_rank_max=70.0,
                max_premium_per_trade=500.0,
                max_contracts_per_trade=2,
                roll_dte_threshold=45,
                profit_take_pct=30.0,
                max_loss_pct=20.0,
            ),
        )
        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {})
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (None, None))

        account_report(conn, "acct_leaps")
        out = capsys.readouterr().out
        assert "LEAPs Parameters:" in out
        assert "LEAPs Options Filters:" in out
        assert "LEAPs/Options Risk Limits:" in out

    def test_rotation_account_header_shows_base_and_active_strategy(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        create_account(conn, "acct_rot", "Trend", 1000.0, "SPY")
        conn.execute(
            """
            UPDATE accounts
            SET rotation_enabled = 1,
                rotation_active_strategy = 'mean_reversion'
            WHERE name = 'acct_rot'
            """
        )
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {})
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (None, None))

        account_report(conn, "acct_rot")
        out = capsys.readouterr().out
        assert "base_strategy=Trend | active_strategy=mean_reversion" in out


class TestCompareStrategies:
    def test_no_accounts_message(self, conn, capsys) -> None:
        compare_strategies(conn, lookback=5)
        out = capsys.readouterr().out
        assert "No paper accounts found." in out

    def test_outputs_summary_and_na_benchmark(self, conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        create_account(conn, "acct_cmp", "Trend", 1000.0, "SPY", config=AccountConfig(descriptive_name="Compare"))
        account = get_account(conn, "acct_cmp")
        _insert_trade(conn, account["id"], "AAPL", 1.0, 100.0)
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda _tickers: {"AAPL": 101.0})
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (None, None))

        compare_strategies(conn, lookback=5)
        out = capsys.readouterr().out
        assert "Account policy comparison (current paper account state):" in out
        assert "not canonical strategy research scores" in out
        assert "display_name=Compare" in out
        assert "account_policy=base_strategy=Trend | active_strategy=Trend | benchmark=SPY" in out
        assert "benchmark_equity=N/A benchmark_return=N/A account_alpha=N/A" in out
        assert "positions: AAPL:1.00" in out

    def test_truncates_positions_list(self, conn, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        create_account(conn, "acct_many", "Trend", 10000.0, "SPY", config=AccountConfig(descriptive_name="Many"))
        account = get_account(conn, "acct_many")

        tickers = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA"]
        for i, ticker in enumerate(tickers):
            _insert_trade(conn, account["id"], ticker, 1.0, 100.0 + i, trade_time=f"2026-01-01T00:00:0{i}Z")
        conn.commit()

        monkeypatch.setattr("trading.services.reporting_service.fetch_latest_prices", lambda symbols: {symbol: 110.0 for symbol in symbols})
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (10100.0, 1.0))
        monkeypatch.setattr("trading.services.reporting_service.infer_overall_trend", lambda *_args, **_kwargs: "up")

        compare_strategies(conn, lookback=5)
        out = capsys.readouterr().out
        assert "positions: AAPL:1.00, AMZN:1.00, GOOG:1.00, META:1.00, MSFT:1.00, ..." in out

    def test_outputs_none_positions_for_account_without_trades(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        create_account(conn, "acct_none", "Trend", 1000.0, "SPY", config=AccountConfig(descriptive_name="No Trades"))
        monkeypatch.setattr("trading.services.reporting_service.benchmark_stats", lambda *_args: (None, None))

        compare_strategies(conn, lookback=5)
        out = capsys.readouterr().out
        assert "positions: none" in out


class TestSnapshots:
    def test_snapshot_account_inserts_and_defaults_time(
        self,
        conn,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        create_account(conn, "acct_snap", "Trend", 1000.0, "SPY")
        monkeypatch.setattr(
            reporting_service,
            "account_report",
            lambda _conn, _name: (
                {
                    "cash": 900.0,
                    "market_value": 150.0,
                    "equity": 1050.0,
                    "realized_pnl": 20.0,
                    "unrealized_pnl": 30.0,
                    "strategy_return_pct": 5.0,
                },
                {"AAPL": 1.0},
            ),
        )
        monkeypatch.setattr(reporting_service, "utc_now_iso", lambda: "2099-01-01T00:00:00Z")

        snapshot_account(conn, "acct_snap", snapshot_time=None)
        out = capsys.readouterr().out
        assert "Snapshot saved." in out

        account = get_account(conn, "acct_snap")
        row = conn.execute(
            "SELECT snapshot_time, equity FROM equity_snapshots WHERE account_id = ?",
            (account["id"],),
        ).fetchone()
        assert row is not None
        assert row["snapshot_time"] == "2099-01-01T00:00:00Z"
        assert float(row["equity"]) == pytest.approx(1050.0)

    def test_show_snapshots_empty_and_rows(self, conn, capsys) -> None:
        create_account(conn, "acct_show", "Trend", 1000.0, "SPY")

        show_snapshots(conn, "acct_show", limit=5)
        out_empty = capsys.readouterr().out
        assert "No snapshots found." in out_empty

        account = get_account(conn, "acct_show")
        conn.execute(
            """
            INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account["id"], "2026-03-01T00:00:00Z", 900.0, 100.0, 1000.0, 10.0, 15.0),
        )
        conn.commit()

        show_snapshots(conn, "acct_show", limit=5)
        out_rows = capsys.readouterr().out
        assert "Snapshot history (latest 5) for acct_show:" in out_rows
        assert "equity=1000.00" in out_rows
