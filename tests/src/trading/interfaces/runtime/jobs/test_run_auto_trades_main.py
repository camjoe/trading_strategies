from __future__ import annotations

from unittest.mock import Mock

import pytest

from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_run_auto_trades_args,
    run_auto_trades as module,
)


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def install_main_args(monkeypatch, **overrides):
    monkeypatch.setattr(module, "parse_args", lambda: make_run_auto_trades_args(**overrides))


def test_main_validation_errors(monkeypatch) -> None:
    install_main_args(monkeypatch, min_trades=0, max_trades=1)

    with pytest.raises(ValueError, match="min-trades"):
        module.main()


def test_main_happy_path_dispatches_accounts(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_main_args(
        monkeypatch,
        min_trades=1,
        max_trades=2,
        seed=123,
        accounts="acct1,acct2",
        fee=1.0,
        execution_mode="sleeve",
    )
    monkeypatch.setattr(
        module, "resolve_market_inputs", lambda _p: (["AAPL", "MSFT"], {"AAPL": 100.0, "MSFT": 200.0}, {"AAPL": 40.0})
    )
    monkeypatch.setattr(module, "ensure_db", lambda: conn)
    run_accounts_mock = Mock(return_value=[("acct1", 2), ("acct2", 2)])
    monkeypatch.setattr(module, "run_accounts", run_accounts_mock)

    module.main()

    out = capsys.readouterr().out
    assert "acct1: executed 2 trades" in out
    assert "acct2: executed 2 trades" in out
    assert conn.closed is True
    assert run_accounts_mock.call_args.kwargs["execution_mode"] == "sleeve"


def test_main_additional_validation_paths(monkeypatch) -> None:
    install_main_args(monkeypatch, min_trades=2, max_trades=1)

    with pytest.raises(ValueError, match="max-trades"):
        module.main()

    install_main_args(monkeypatch, min_trades=2, max_trades=2, accounts="  ,   ")

    with pytest.raises(ValueError, match="No accounts"):
        module.main()


def test_main_empty_universe_and_no_prices(monkeypatch) -> None:
    install_main_args(monkeypatch)
    monkeypatch.setattr(
        module, "resolve_market_inputs", lambda _p: (_ for _ in ()).throw(ValueError("Ticker universe is empty."))
    )

    with pytest.raises(ValueError, match="Ticker universe is empty"):
        module.main()

    monkeypatch.setattr(
        module,
        "resolve_market_inputs",
        lambda _p: (_ for _ in ()).throw(ValueError("Could not fetch any prices for ticker universe.")),
    )

    with pytest.raises(ValueError, match="Could not fetch any prices"):
        module.main()


def test_main_closes_connection_when_run_accounts_fails(monkeypatch) -> None:
    conn = FakeConn()
    install_main_args(monkeypatch)
    monkeypatch.setattr(module, "resolve_market_inputs", lambda _p: (["AAPL"], {"AAPL": 100.0}, {}))
    monkeypatch.setattr(module, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        module,
        "run_accounts",
        Mock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        module.main()

    assert conn.closed is True


def test_run_auto_trades_module_entrypoint(monkeypatch) -> None:
    import sys
    import infrastructure.database.init as init_module
    import trading.services.auto_trading as auto_trading_module

    conn = FakeConn()
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(auto_trading_module, "validate_trade_count_range", lambda *_a: None)
    monkeypatch.setattr(auto_trading_module, "validate_execution_mode", lambda value: value)
    monkeypatch.setattr(auto_trading_module, "resolve_account_names", lambda _accounts: ["acct1"])
    monkeypatch.setattr(
        auto_trading_module,
        "resolve_market_inputs",
        lambda _path: (["AAPL"], {"AAPL": 100.0}, {"AAPL": 40.0}),
    )
    monkeypatch.setattr(auto_trading_module, "run_accounts", lambda *_a, **_kw: [("acct1", 1)])
    monkeypatch.setattr(sys, "argv", ["run_auto_trades", "--accounts", "acct1", "--seed", "7"])

    run_module_as_main(module.__name__)

    assert conn.closed is True
