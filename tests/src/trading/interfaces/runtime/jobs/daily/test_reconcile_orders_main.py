from __future__ import annotations

import argparse
from unittest.mock import Mock

import pytest

import infrastructure.database.connection as init_module
from tests.src.trading.interfaces.runtime.jobs.loaders import load_runtime_job

RECONCILE_ORDERS_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.reconcile_orders"
module = load_runtime_job(RECONCILE_ORDERS_MODULE)


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def install_args(monkeypatch, accounts: str) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: argparse.Namespace(accounts=accounts))


def test_main_reconciles_each_account_and_reports_counts(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_args(monkeypatch, "acct1,acct2")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    reconcile = Mock(side_effect=[2, 0])
    monkeypatch.setattr(module, "reconcile_open_broker_orders", reconcile)

    module.main()

    out = capsys.readouterr().out
    assert "acct1: reconciled 2 newly filled order(s)" in out
    assert "acct2: reconciled 0 newly filled order(s)" in out
    assert [call.args[1] for call in reconcile.call_args_list] == ["account:acct1", "account:acct2"]
    assert conn.closed is True


def test_main_skips_blank_account_names(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_args(monkeypatch, " acct1 , , ")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    reconcile = Mock(return_value=0)
    monkeypatch.setattr(module, "reconcile_open_broker_orders", reconcile)

    module.main()

    assert reconcile.call_count == 1
    assert "acct1: reconciled 0 newly filled order(s)" in capsys.readouterr().out


def test_main_closes_connection_when_reconciliation_fails(monkeypatch) -> None:
    conn = FakeConn()
    install_args(monkeypatch, "acct1")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    monkeypatch.setattr(
        module,
        "reconcile_open_broker_orders",
        Mock(side_effect=RuntimeError("broker unreachable")),
    )

    with pytest.raises(RuntimeError, match="broker unreachable"):
        module.main()

    assert conn.closed is True
