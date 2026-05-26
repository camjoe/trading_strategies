from types import SimpleNamespace

import pytest

from tests.trading.interfaces.helpers import run_module_as_main
from trading.interfaces.cli import main as cli_main
from tests.trading.interfaces.cli.helpers import configure_account_args, install_main_harness


def test_main_trade_dispatches_and_closes_connection(monkeypatch, capsys) -> None:
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
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    def fake_record_trade(conn, **kwargs):
        captured["conn"] = conn
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli_main, "record_trade", fake_record_trade)

    cli_main.main()

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


def test_main_configure_account_conflicting_learning_flags_errors(monkeypatch) -> None:
    args = configure_account_args(learning_enabled=True, learning_disabled=True)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(
        cli_main,
        "configure_account",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    with pytest.raises(RuntimeError, match="Use only one of --learning-enabled or --learning-disabled"):
        cli_main.main()

    assert fake_conn.closed is True


def test_main_unknown_command_errors_and_closes_connection(monkeypatch) -> None:
    fake_conn = install_main_harness(monkeypatch, cli_main, SimpleNamespace(command="unknown"))

    with pytest.raises(RuntimeError, match="Unsupported command: unknown"):
        cli_main.main()

    assert fake_conn.closed is True


def test_main_create_account_defaults_learning_disabled(monkeypatch) -> None:
    args = configure_account_args(
        command="create-account",
        name="acct1",
        strategy="Momentum",
        initial_cash=5000.0,
        benchmark="SPY",
        learning_enabled=False,
    )
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured: dict[str, object] = {}

    def fake_create_account(conn, name, strategy, initial_cash, benchmark, **kwargs):
        captured["conn"] = conn
        captured["name"] = name
        captured["strategy"] = strategy
        captured["initial_cash"] = initial_cash
        captured["benchmark"] = benchmark
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli_main, "create_account", fake_create_account)

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["name"] == "acct1"
    assert captured["strategy"] == "Momentum"
    assert captured["initial_cash"] == 5000.0
    assert captured["benchmark"] == "SPY"
    assert captured["kwargs"]["config"].learning_enabled is False
    assert fake_conn.closed is True


def test_main_configure_account_success_path_prints_update(monkeypatch, capsys) -> None:
    args = configure_account_args(command="configure-account", learning_enabled=True)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    def fake_configure_account(conn, account_name, **kwargs):
        captured["conn"] = conn
        captured["account_name"] = account_name
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli_main, "configure_account", fake_configure_account)

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["account_name"] == "acct1"
    assert captured["kwargs"]["config"].learning_enabled is True
    assert "Updated account configuration for 'acct1'." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_set_benchmark_uppercases_print(monkeypatch, capsys) -> None:
    args = SimpleNamespace(command="set-benchmark", account="acct1", benchmark="qqq")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    def fake_set_benchmark(conn, account, benchmark):
        captured["conn"] = conn
        captured["account"] = account
        captured["benchmark"] = benchmark

    monkeypatch.setattr(cli_main, "set_benchmark", fake_set_benchmark)

    cli_main.main()

    assert captured == {"conn": fake_conn, "account": "acct1", "benchmark": "qqq"}
    assert "Updated benchmark for 'acct1' to 'QQQ'." in capsys.readouterr().out
    assert fake_conn.closed is True


def test_main_list_accounts_dispatches(monkeypatch) -> None:
    args = SimpleNamespace(command="list-accounts")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}

    monkeypatch.setattr(cli_main, "list_accounts", lambda conn: captured.update({"conn": conn}))

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert fake_conn.closed is True


def test_main_module_entrypoint_runs_under_main_name(monkeypatch) -> None:
    import trading.database.db_config as db_config_module
    import trading.database.db_init as db_init_module
    import trading.interfaces.cli.commands as commands_module
    import trading.interfaces.cli.handlers.router as router_module

    class _FakeParser:
        def parse_args(self):
            return SimpleNamespace(command="list-accounts")

    class _FakeConn:
        def close(self) -> None:
            return None

    dispatched: dict[str, object] = {}
    monkeypatch.setattr(commands_module, "build_parser", lambda: _FakeParser())
    monkeypatch.setattr(db_init_module, "ensure_db", lambda: _FakeConn())
    monkeypatch.setattr(db_config_module, "get_db_path", lambda: "paper.db")
    monkeypatch.setattr(
        router_module,
        "dispatch_command",
        lambda conn, args, parser, **kwargs: dispatched.update(
            {"command": args.command, "db_path": kwargs["db_path"]}
        ),
    )

    run_module_as_main(cli_main.__name__)

    assert dispatched == {"command": "list-accounts", "db_path": "paper.db"}
