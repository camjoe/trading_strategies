from types import SimpleNamespace

from trading.backtesting.report_models import BacktestLeaderboardEntry
from trading.interfaces.cli import main as cli_main
from tests.support import install_main_harness


def test_main_backtest_dispatches_and_prints_summary(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="backtest",
        account="acct1",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name="smoke",
        allow_approximate_leaps=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    class _Result:
        run_id = 7
        account_name = "acct1"
        start_date = "2026-01-01"
        end_date = "2026-03-01"
        trade_count = 5
        ending_equity = 10450.0
        total_return_pct = 4.5
        max_drawdown_pct = -2.0
        benchmark_return_pct = 3.0
        alpha_pct = 1.5
        sharpe_ratio = None
        sortino_ratio = None
        calmar_ratio = None
        win_rate_pct = None
        profit_factor = None
        avg_trade_return_pct = None
        warnings = ["daily bars only"]

    monkeypatch.setattr(
        cli_main,
        "run_backtest",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or _Result(),
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_name == "acct1"
    out = capsys.readouterr().out
    assert "Backtest complete: run_id=7" in out
    assert "Benchmark Return: 3.00% | Alpha: 1.50%" in out
    assert "Backtest safeguards / approximation notes:" in out
    assert fake_conn.closed is True


def test_main_backtest_without_benchmark_prints_unavailable(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="backtest",
        account="acct1",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name=None,
        allow_approximate_leaps=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)

    class _Result:
        run_id = 8
        account_name = "acct1"
        start_date = "2026-01-01"
        end_date = "2026-03-01"
        trade_count = 3
        ending_equity = 10300.0
        total_return_pct = 3.0
        max_drawdown_pct = -1.0
        benchmark_return_pct = None
        alpha_pct = None
        sharpe_ratio = None
        sortino_ratio = None
        calmar_ratio = None
        win_rate_pct = None
        profit_factor = None
        avg_trade_return_pct = None
        warnings = []

    monkeypatch.setattr(cli_main, "run_backtest", lambda _conn, _cfg: _Result())

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest complete: run_id=8" in out
    assert "Benchmark comparison unavailable for selected date range." in out
    assert "Backtest safeguards / approximation notes:" not in out
    assert fake_conn.closed is True


def test_main_backtest_report_dispatches(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="backtest-report", run_id=11)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)

    monkeypatch.setattr(
        cli_main,
        "backtest_report",
        lambda _conn, run_id: {
            "run_id": run_id,
            "run_name": "wf-1",
            "account_name": "acct1",
            "strategy": "Trend",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "created_at": "2026-03-14T00:00:00Z",
            "trade_count": 2,
            "starting_equity": 10000.0,
            "ending_equity": 10100.0,
            "total_return_pct": 1.0,
            "max_drawdown_pct": -0.5,
            "slippage_bps": 5.0,
            "fee_per_trade": 0.0,
            "tickers_file": "trading/config/trade_universe.txt",
            "warnings": "daily bars only",
        },
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest Run 11 (wf-1)" in out
    assert "Safeguards / notes: daily bars only" in out
    assert fake_conn.closed is True


def test_main_backtest_report_without_warnings_omits_notes_line(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="backtest-report", run_id=99)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)

    monkeypatch.setattr(
        cli_main,
        "backtest_report",
        lambda _conn, _run_id: {
            "run_id": 99,
            "run_name": None,
            "account_name": "acct1",
            "strategy": "Trend",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "created_at": "2026-03-14T00:00:00Z",
            "trade_count": 2,
            "starting_equity": 10000.0,
            "ending_equity": 10100.0,
            "total_return_pct": 1.0,
            "max_drawdown_pct": -0.5,
            "slippage_bps": 5.0,
            "fee_per_trade": 0.0,
            "tickers_file": "trading/config/trade_universe.txt",
            "warnings": "",
        },
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest Run 99 (unnamed)" in out
    assert "Safeguards / notes:" not in out
    assert fake_conn.closed is True


def test_main_backtest_walk_forward_dispatches(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="backtest-walk-forward",
        account="acct1",
        tickers_file="trading/config/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-31",
        lookback_months=None,
        test_months=1,
        step_months=1,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix="wf",
        allow_approximate_leaps=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    class _Summary:
        account_name = "acct1"
        start_date = "2026-01-01"
        end_date = "2026-03-31"
        window_count = 3
        run_ids = [101, 102, 103]
        average_return_pct = 1.2
        median_return_pct = 1.0
        best_return_pct = 2.3
        worst_return_pct = 0.1

    monkeypatch.setattr(
        cli_main,
        "run_walk_forward_backtest",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or _Summary(),
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].test_months == 1
    out = capsys.readouterr().out
    assert "Walk-forward complete: account=acct1" in out
    assert "Generated run ids: 101, 102, 103" in out
    assert fake_conn.closed is True


def test_main_backtest_walk_forward_prints_run_id_ellipsis(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="backtest-walk-forward",
        account="acct1",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-31",
        lookback_months=None,
        test_months=1,
        step_months=1,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix="wf",
        allow_approximate_leaps=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)

    class _Summary:
        account_name = "acct1"
        start_date = "2026-01-01"
        end_date = "2026-03-31"
        window_count = 12
        run_ids = list(range(101, 113))
        average_return_pct = 1.2
        median_return_pct = 1.0
        best_return_pct = 2.3
        worst_return_pct = 0.1

    monkeypatch.setattr(cli_main, "run_walk_forward_backtest", lambda _conn, _cfg: _Summary())

    cli_main.main()

    out = capsys.readouterr().out
    assert "Generated run ids: 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, ..." in out
    assert fake_conn.closed is True


def test_main_backtest_leaderboard_dispatches(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="backtest-leaderboard", limit=5, account=None, strategy="trend")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)

    monkeypatch.setattr(
        cli_main,
        "backtest_leaderboard_entries",
        lambda _conn, *, limit, account_name, strategy: [
            BacktestLeaderboardEntry(
                run_id=9,
                run_name="batch_01",
                account_name="acct1",
                strategy="trend_v1",
                start_date="2026-01-01",
                end_date="2026-03-01",
                created_at="2026-03-17T01:00:00Z",
                trade_count=8,
                ending_equity=10500.0,
                total_return_pct=5.0,
                max_drawdown_pct=-1.2,
                benchmark_return_pct=2.0,
                alpha_pct=3.0,
            )
        ],
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "run_id,run_name,account_name,strategy" in out
    assert "9,batch_01,acct1,trend_v1" in out
    assert fake_conn.closed is True


def test_main_backtest_leaderboard_no_rows_prints_message(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="backtest-leaderboard", limit=10, account=None, strategy=None)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(cli_main, "backtest_leaderboard_entries", lambda *_args, **_kwargs: [])

    cli_main.main()

    out = capsys.readouterr().out
    assert "No backtest runs matched the selected filters." in out
    assert fake_conn.closed is True


def test_main_backtest_batch_dispatches(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="backtest-batch",
        accounts="acct1, acct2",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix="batch",
        allow_approximate_leaps=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    class _Result:
        def __init__(self, account_name: str, run_id: int, ret: float):
            self.account_name = account_name
            self.run_id = run_id
            self.total_return_pct = ret
            self.max_drawdown_pct = -1.0
            self.ending_equity = 10000.0 + ret
            self.trade_count = 3

    monkeypatch.setattr(
        cli_main,
        "run_backtest_batch",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or [_Result("acct2", 22, 3.0), _Result("acct1", 21, 1.0)],
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_names == ["acct1", "acct2"]
    out = capsys.readouterr().out
    assert "Backtest batch complete." in out
    assert "1,acct2,22,3.0000" in out
    assert fake_conn.closed is True
