from __future__ import annotations

from unittest.mock import Mock

import pytest

import infrastructure.database.connection as init_module
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_run_auto_trades_args,
    run_auto_trades as module,
)
from trading.models.execution import AccountRunResult


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def install_main_args(monkeypatch, **overrides):
    monkeypatch.setattr(module, "parse_args", lambda: make_run_auto_trades_args(**overrides))


def test_main_validation_errors(monkeypatch) -> None:
    install_main_args(monkeypatch, max_trades=0)

    with pytest.raises(ValueError, match="max-trades"):
        module.main()


def test_main_happy_path_dispatches_accounts(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_main_args(
        monkeypatch,
        max_trades=2,
        seed=123,
        accounts="acct1,acct2",
        fee=1.0,
    )
    monkeypatch.setattr(
        module,
        "resolve_market_inputs",
        lambda _p, **_kwargs: (["AAPL", "MSFT"], {"AAPL": 100.0, "MSFT": 200.0}, {"AAPL": 40.0}, {}),
    )
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    run_accounts_mock = Mock(
        return_value=[
            AccountRunResult(account_name="acct1", submitted_count=2),
            AccountRunResult(account_name="acct2", submitted_count=2),
        ]
    )
    monkeypatch.setattr(module, "run_accounts", run_accounts_mock)

    assert module.main() == 0

    out = capsys.readouterr().out
    assert "acct1: executed 2 trades" in out
    assert "acct2: executed 2 trades" in out
    assert conn.closed is True


def test_main_additional_validation_paths(monkeypatch) -> None:
    install_main_args(monkeypatch, max_trades=2, accounts="  ,   ")

    with pytest.raises(ValueError, match="No accounts"):
        module.main()


def test_main_empty_universe_and_no_prices(monkeypatch) -> None:
    install_main_args(monkeypatch)
    monkeypatch.setattr(
        module,
        "resolve_market_inputs",
        lambda _p, **_kwargs: (_ for _ in ()).throw(ValueError("Ticker universe is empty.")),
    )

    with pytest.raises(ValueError, match="Ticker universe is empty"):
        module.main()

    monkeypatch.setattr(
        module,
        "resolve_market_inputs",
        lambda _p, **_kwargs: (_ for _ in ()).throw(ValueError("Could not fetch any prices for ticker universe.")),
    )

    with pytest.raises(ValueError, match="Could not fetch any prices"):
        module.main()


def test_main_closes_connection_when_run_accounts_fails(monkeypatch) -> None:
    conn = FakeConn()
    install_main_args(monkeypatch)
    monkeypatch.setattr(module, "resolve_market_inputs", lambda _p, **_kwargs: (["AAPL"], {"AAPL": 100.0}, {}, {}))
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
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

    import trading.services.auto_trading as auto_trading_module

    conn = FakeConn()
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(auto_trading_module, "validate_trade_count_range", lambda *_a: None)
    monkeypatch.setattr(auto_trading_module, "resolve_account_names", lambda _accounts: ["acct1"])
    monkeypatch.setattr(
        auto_trading_module,
        "resolve_market_inputs",
        lambda _path, **_kwargs: (["AAPL"], {"AAPL": 100.0}, {"AAPL": 40.0}, {}),
    )
    monkeypatch.setattr(
        auto_trading_module,
        "run_accounts",
        lambda *_a, **_kw: [AccountRunResult(account_name="acct1", submitted_count=1)],
    )
    monkeypatch.setattr(sys, "argv", ["run_auto_trades", "--accounts", "acct1", "--seed", "7"])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 0
    assert conn.closed is True


def test_main_exits_non_zero_on_a_broker_anomaly(monkeypatch, capsys) -> None:
    """A broker failure mid-submission fails the step: real orders may be in an unknown state."""
    conn = FakeConn()
    install_main_args(monkeypatch, accounts="acct1,acct2")
    monkeypatch.setattr(module, "resolve_market_inputs", lambda _p, **_kwargs: (["AAPL"], {"AAPL": 100.0}, {}, {}))
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        module,
        "run_accounts",
        Mock(
            return_value=[
                AccountRunResult(account_name="acct1", submitted_count=2),
                AccountRunResult(
                    account_name="acct2",
                    submitted_count=1,
                    kill_switch_reasons=("broker_api_anomaly",),
                ),
            ]
        ),
    )

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "acct2: executed 1 trades (halted: broker_api_anomaly)" in out
    assert "Broker API anomaly during submission for: acct2" in out


def test_main_stays_green_for_a_non_broker_kill_switch(monkeypatch, capsys) -> None:
    """Stale prices and reconciliation halts are controls working, not run failures."""
    conn = FakeConn()
    install_main_args(monkeypatch, accounts="acct1")
    monkeypatch.setattr(module, "resolve_market_inputs", lambda _p, **_kwargs: (["AAPL"], {"AAPL": 100.0}, {}, {}))
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(
        module,
        "run_accounts",
        Mock(
            return_value=[
                AccountRunResult(
                    account_name="acct1",
                    submitted_count=0,
                    kill_switch_reasons=("stale_price_data",),
                )
            ]
        ),
    )

    assert module.main() == 0
    assert "acct1: executed 0 trades (halted: stale_price_data)" in capsys.readouterr().out
