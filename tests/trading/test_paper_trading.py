from pathlib import Path
from types import SimpleNamespace

import pytest

from trading.interfaces.cli import main as paper_trading
from trading.backtesting.report_models import BacktestLeaderboardEntry


class _FakeParser:
    def __init__(self, args):
        self._args = args

    def parse_args(self):
        return self._args

    def error(self, message: str):
        raise RuntimeError(message)


class _FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _configure_args(**overrides):
    base = {
        "command": "configure-account",
        "account": "acct1",
        "display_name": None,
        "goal_min_return_pct": None,
        "goal_max_return_pct": None,
        "goal_period": None,
        "learning_enabled": False,
        "learning_disabled": False,
        "risk_policy": None,
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "instrument_mode": None,
        "option_strike_offset_pct": None,
        "option_min_dte": None,
        "option_max_dte": None,
        "option_type": None,
        "target_delta_min": None,
        "target_delta_max": None,
        "max_premium_per_trade": None,
        "max_contracts_per_trade": None,
        "iv_rank_min": None,
        "iv_rank_max": None,
        "roll_dte_threshold": None,
        "profit_take_pct": None,
        "max_loss_pct": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_main_trade_dispatches_and_closes_connection(monkeypatch, capsys):
    fake_conn = _FakeConn()
    args = SimpleNamespace(
        command="trade",
        account="acct1",
        side="buy",
        ticker="AAPL",
        qty=2,
        price=100.5,
        fee=1.25,
        time="2026-03-14T10:00:00",
        note="test",
    )

    captured = {}

    def fake_record_trade(conn, **kwargs):
        captured["conn"] = conn
        captured["kwargs"] = kwargs

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "record_trade", fake_record_trade)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["kwargs"] == {
        "account_name": "acct1",
        "side": "buy",
        "ticker": "AAPL",
        "qty": 2,
        "price": 100.5,
        "fee": 1.25,
        "trade_time": "2026-03-14T10:00:00",
        "note": "test",
    }
    assert "Trade recorded." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_configure_account_conflicting_learning_flags_errors(monkeypatch):
    fake_conn = _FakeConn()
    args = _configure_args(learning_enabled=True, learning_disabled=True)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("configure_account should not be called")

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "configure_account", fail_if_called)

    with pytest.raises(RuntimeError, match="Use only one of --learning-enabled or --learning-disabled"):
        paper_trading.main()

    assert fake_conn.closed is True


def test_main_unknown_command_errors_and_closes_connection(monkeypatch):
    fake_conn = _FakeConn()
    args = SimpleNamespace(command="unknown")

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)

    with pytest.raises(RuntimeError, match="Unsupported command: unknown"):
        paper_trading.main()

    assert fake_conn.closed is True


def test_common_account_config_kwargs_create_sets_learning_enabled():
    args = _configure_args(command="create-account", learning_enabled=True)
    kwargs = paper_trading._common_account_config_kwargs(args, include_learning_disabled=False)
    assert kwargs.learning_enabled is True


def test_main_create_account_defaults_learning_disabled(monkeypatch):
    fake_conn = _FakeConn()
    args = _configure_args(
        command="create-account",
        name="acct1",
        strategy="Momentum",
        initial_cash=5000.0,
        benchmark="SPY",
        learning_enabled=False,
    )

    captured: dict[str, object] = {}

    def fake_create_account(conn, name, strategy, initial_cash, benchmark, **kwargs):
        captured["conn"] = conn
        captured["name"] = name
        captured["strategy"] = strategy
        captured["initial_cash"] = initial_cash
        captured["benchmark"] = benchmark
        captured["kwargs"] = kwargs

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "create_account", fake_create_account)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["name"] == "acct1"
    assert captured["strategy"] == "Momentum"
    assert captured["initial_cash"] == 5000.0
    assert captured["benchmark"] == "SPY"
    assert captured["kwargs"]["config"].learning_enabled is False
    assert fake_conn.closed is True


def test_main_backtest_dispatches_and_prints_summary(monkeypatch, capsys):
    fake_conn = _FakeConn()
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
        warnings = ["daily bars only"]

    def fake_run_backtest(conn, cfg):
        captured["conn"] = conn
        captured["cfg"] = cfg
        return _Result()

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "run_backtest", fake_run_backtest)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_name == "acct1"
    out = capsys.readouterr().out
    assert "Backtest complete: run_id=7" in out
    assert "Benchmark Return: 3.00% | Alpha: 1.50%" in out
    assert "Backtest safeguards / approximation notes:" in out
    assert fake_conn.closed is True


def test_main_backtest_report_dispatches(monkeypatch, capsys):
    fake_conn = _FakeConn()
    args = SimpleNamespace(command="backtest-report", run_id=11)

    def fake_backtest_report(_conn, run_id):
        assert run_id == 11
        return {
            "run_id": 11,
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
        }

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "backtest_report", fake_backtest_report)

    paper_trading.main()

    out = capsys.readouterr().out
    assert "Backtest Run 11 (wf-1)" in out
    assert "Safeguards / notes: daily bars only" in out
    assert fake_conn.closed is True


def test_main_backtest_walk_forward_dispatches(monkeypatch, capsys):
    fake_conn = _FakeConn()
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

    def fake_run_walk_forward_backtest(conn, cfg):
        captured["conn"] = conn
        captured["cfg"] = cfg
        return _Summary()

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "run_walk_forward_backtest", fake_run_walk_forward_backtest)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].test_months == 1
    out = capsys.readouterr().out
    assert "Walk-forward complete: account=acct1" in out
    assert "Generated run ids: 101, 102, 103" in out
    assert fake_conn.closed is True


def test_main_backtest_leaderboard_dispatches(monkeypatch, capsys):
    fake_conn = _FakeConn()
    args = SimpleNamespace(
        command="backtest-leaderboard",
        limit=5,
        account=None,
        strategy="trend",
    )

    def fake_backtest_leaderboard_entries(_conn, *, limit, account_name, strategy):
        assert limit == 5
        assert account_name is None
        assert strategy == "trend"
        return [
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
        ]

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "backtest_leaderboard_entries", fake_backtest_leaderboard_entries)

    paper_trading.main()

    out = capsys.readouterr().out
    assert "run_id,run_name,account_name,strategy" in out
    assert "9,batch_01,acct1,trend_v1" in out
    assert fake_conn.closed is True


def test_main_backtest_batch_dispatches(monkeypatch, capsys):
    fake_conn = _FakeConn()
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

    captured = {}

    class _Result:
        def __init__(self, account_name: str, run_id: int, ret: float):
            self.account_name = account_name
            self.run_id = run_id
            self.total_return_pct = ret
            self.max_drawdown_pct = -1.0
            self.ending_equity = 10000.0 + ret
            self.trade_count = 3

    def fake_run_backtest_batch(conn, cfg):
        captured["conn"] = conn
        captured["cfg"] = cfg
        return [_Result("acct2", 22, 3.0), _Result("acct1", 21, 1.0)]

    monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
    monkeypatch.setattr(paper_trading, "run_backtest_batch", fake_run_backtest_batch)

    paper_trading.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_names == ["acct1", "acct2"]
    out = capsys.readouterr().out
    assert "Backtest batch complete." in out
    assert "1,acct2,22,3.0000" in out
    assert fake_conn.closed is True


class TestLearningFlagResolution:
    def test_resolve_learning_enabled_configure_mode_enabled(self):
        args = _configure_args(learning_enabled=True, learning_disabled=False)

        resolved = paper_trading._resolve_learning_enabled(args, include_learning_disabled=True)

        assert resolved is True

    def test_resolve_learning_enabled_configure_mode_disabled(self):
        args = _configure_args(learning_enabled=False, learning_disabled=True)

        resolved = paper_trading._resolve_learning_enabled(args, include_learning_disabled=True)

        assert resolved is False

    def test_resolve_learning_enabled_configure_mode_none(self):
        args = _configure_args(learning_enabled=False, learning_disabled=False)

        resolved = paper_trading._resolve_learning_enabled(args, include_learning_disabled=True)

        assert resolved is None


class TestHandlerOutputsAndEdgeCases:
    def test_main_init_prints_initialized_path(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(command="init")

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)

        paper_trading.main()

        out = capsys.readouterr().out
        assert "Initialized:" in out
        assert fake_conn.closed is True

    def test_main_set_benchmark_uppercases_print(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(command="set-benchmark", account="acct1", benchmark="qqq")

        captured = {}

        def fake_set_benchmark(conn, account, benchmark):
            captured["conn"] = conn
            captured["account"] = account
            captured["benchmark"] = benchmark

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "set_benchmark", fake_set_benchmark)

        paper_trading.main()

        assert captured == {"conn": fake_conn, "account": "acct1", "benchmark": "qqq"}
        assert "Updated benchmark for 'acct1' to 'QQQ'." in capsys.readouterr().out
        assert fake_conn.closed is True

    def test_main_apply_account_profiles_passes_create_missing(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(
            command="apply-account-profiles",
            file="custom_profiles.json",
            no_create_missing=True,
        )

        captured = {}

        def fake_load(path):
            captured["path"] = path
            return [{"name": "acct1"}]

        def fake_apply(conn, profiles, *, create_missing):
            captured["conn"] = conn
            captured["profiles"] = profiles
            captured["create_missing"] = create_missing
            return (1, 2, 3)

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "load_account_profiles", fake_load)
        monkeypatch.setattr(paper_trading, "apply_account_profiles", fake_apply)

        paper_trading.main()

        assert captured["path"] == "custom_profiles.json"
        assert captured["create_missing"] is False
        assert "Applied account profiles: created=1, updated=2, skipped=3." in capsys.readouterr().out
        assert fake_conn.closed is True

    def test_main_apply_account_preset_uses_lowercased_filename(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(
            command="apply-account-preset",
            preset="Conservative",
            no_create_missing=False,
        )

        captured = {}

        def fake_load(path):
            captured["path"] = path
            return [{"name": "acct1"}]

        def fake_apply(conn, profiles, *, create_missing):
            captured["conn"] = conn
            captured["profiles"] = profiles
            captured["create_missing"] = create_missing
            return (0, 1, 0)

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "load_account_profiles", fake_load)
        monkeypatch.setattr(paper_trading, "apply_account_profiles", fake_apply)

        paper_trading.main()

        assert Path(captured["path"]).as_posix().endswith("account_profiles/conservative.json")
        assert captured["create_missing"] is True
        assert "Applied preset 'Conservative': created=0, updated=1, skipped=0." in capsys.readouterr().out
        assert fake_conn.closed is True

    def test_main_backtest_without_benchmark_prints_unavailable(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
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
            warnings = []

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "run_backtest", lambda _conn, _cfg: _Result())

        paper_trading.main()

        out = capsys.readouterr().out
        assert "Backtest complete: run_id=8" in out
        assert "Benchmark comparison unavailable for selected date range." in out
        assert "Backtest safeguards / approximation notes:" not in out
        assert fake_conn.closed is True

    def test_main_backtest_leaderboard_no_rows_prints_message(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(command="backtest-leaderboard", limit=10, account=None, strategy=None)

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "backtest_leaderboard_entries", lambda *_args, **_kwargs: [])

        paper_trading.main()

        out = capsys.readouterr().out
        assert "No backtest runs matched the selected filters." in out
        assert fake_conn.closed is True

    def test_main_backtest_leaderboard_formats_none_optional_fields(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(command="backtest-leaderboard", limit=1, account=None, strategy=None)

        def fake_rows(*_args, **_kwargs):
            return [
                BacktestLeaderboardEntry(
                    run_id=10,
                    run_name=None,
                    account_name="acct1",
                    strategy="trend_v1",
                    start_date="2026-01-01",
                    end_date="2026-01-31",
                    created_at="2026-03-20T00:00:00Z",
                    trade_count=1,
                    ending_equity=10050.0,
                    total_return_pct=0.5,
                    max_drawdown_pct=-0.4,
                    benchmark_return_pct=None,
                    alpha_pct=None,
                )
            ]

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "backtest_leaderboard_entries", fake_rows)

        paper_trading.main()

        out = capsys.readouterr().out
        assert "run_id,run_name,account_name,strategy" in out
        assert "10,,acct1,trend_v1,2026-01-01,2026-01-31,10050.00,0.5000,-0.4000,,,1,2026-03-20T00:00:00Z" in out
        assert fake_conn.closed is True

    def test_main_backtest_report_without_warnings_omits_notes_line(self, monkeypatch, capsys):
        fake_conn = _FakeConn()
        args = SimpleNamespace(command="backtest-report", run_id=99)

        def fake_backtest_report(_conn, _run_id):
            return {
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
            }

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "backtest_report", fake_backtest_report)

        paper_trading.main()

        out = capsys.readouterr().out
        assert "Backtest Run 99 (unnamed)" in out
        assert "Safeguards / notes:" not in out
        assert fake_conn.closed is True


class TestAdditionalCommandDispatch:
    def _run_main(self, monkeypatch, args):
        fake_conn = _FakeConn()
        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        paper_trading.main()
        return fake_conn

    def test_main_configure_account_success_path_prints_update(self, monkeypatch, capsys):
        args = _configure_args(command="configure-account", learning_enabled=True, learning_disabled=False)
        captured = {}

        def fake_configure_account(conn, account_name, **kwargs):
            captured["conn"] = conn
            captured["account_name"] = account_name
            captured["kwargs"] = kwargs

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        fake_conn = _FakeConn()
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "configure_account", fake_configure_account)

        paper_trading.main()

        assert captured["conn"] is fake_conn
        assert captured["account_name"] == "acct1"
        assert captured["kwargs"]["config"].learning_enabled is True
        assert "Updated account configuration for 'acct1'." in capsys.readouterr().out
        assert fake_conn.closed is True

    def test_main_list_accounts_dispatches(self, monkeypatch):
        args = SimpleNamespace(command="list-accounts")
        captured = {}

        def fake_list_accounts(conn):
            captured["conn"] = conn

        monkeypatch.setattr(paper_trading, "list_accounts", fake_list_accounts)
        fake_conn = self._run_main(monkeypatch, args)

        assert captured["conn"] is fake_conn
        assert fake_conn.closed is True

    def test_main_report_dispatches(self, monkeypatch):
        args = SimpleNamespace(command="report", account="acct1")
        captured = {}

        def fake_account_report(conn, account):
            captured["conn"] = conn
            captured["account"] = account

        monkeypatch.setattr(paper_trading, "account_report", fake_account_report)
        fake_conn = self._run_main(monkeypatch, args)

        assert captured == {"conn": fake_conn, "account": "acct1"}
        assert fake_conn.closed is True

    def test_main_snapshot_dispatches(self, monkeypatch):
        args = SimpleNamespace(command="snapshot", account="acct1", time="2026-03-21T10:15:00")
        captured = {}

        def fake_snapshot_account(conn, account, snap_time):
            captured["conn"] = conn
            captured["account"] = account
            captured["snap_time"] = snap_time

        monkeypatch.setattr(paper_trading, "snapshot_account", fake_snapshot_account)
        fake_conn = self._run_main(monkeypatch, args)

        assert captured == {
            "conn": fake_conn,
            "account": "acct1",
            "snap_time": "2026-03-21T10:15:00",
        }
        assert fake_conn.closed is True

    def test_main_snapshot_history_dispatches(self, monkeypatch):
        args = SimpleNamespace(command="snapshot-history", account="acct1", limit=25)
        captured = {}

        def fake_show_snapshots(conn, account, limit):
            captured["conn"] = conn
            captured["account"] = account
            captured["limit"] = limit

        monkeypatch.setattr(paper_trading, "show_snapshots", fake_show_snapshots)
        fake_conn = self._run_main(monkeypatch, args)

        assert captured == {"conn": fake_conn, "account": "acct1", "limit": 25}
        assert fake_conn.closed is True

    def test_main_compare_strategies_dispatches(self, monkeypatch):
        args = SimpleNamespace(command="compare-strategies", lookback=60)
        captured = {}

        def fake_compare_strategies(conn, lookback):
            captured["conn"] = conn
            captured["lookback"] = lookback

        monkeypatch.setattr(paper_trading, "compare_strategies", fake_compare_strategies)
        fake_conn = self._run_main(monkeypatch, args)

        assert captured == {"conn": fake_conn, "lookback": 60}
        assert fake_conn.closed is True

    def test_main_backtest_walk_forward_prints_run_id_ellipsis(self, monkeypatch, capsys):
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

        monkeypatch.setattr(paper_trading, "build_parser", lambda: _FakeParser(args))
        fake_conn = _FakeConn()
        monkeypatch.setattr(paper_trading, "ensure_db", lambda: fake_conn)
        monkeypatch.setattr(paper_trading, "run_walk_forward_backtest", lambda _conn, _cfg: _Summary())

        paper_trading.main()

        out = capsys.readouterr().out
        assert "Generated run ids: 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, ..." in out
        assert fake_conn.closed is True
