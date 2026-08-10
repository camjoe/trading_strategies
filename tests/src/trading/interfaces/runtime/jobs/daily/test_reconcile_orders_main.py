from __future__ import annotations

import argparse
from unittest.mock import Mock

import pytest

import infrastructure.database.connection as init_module
from tests.src.trading.interfaces.runtime.jobs.loaders import load_runtime_job
from trading.services.execution.open_order_reconciliation import ReconciliationOutcome

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
    reconcile = Mock(side_effect=[ReconciliationOutcome(newly_filled=2), ReconciliationOutcome(newly_filled=0)])
    monkeypatch.setattr(module, "reconcile_open_orders", reconcile)

    module.main()

    out = capsys.readouterr().out
    assert "acct1: reconciled 2 newly filled order(s)" in out
    assert "acct2: reconciled 0 newly filled order(s)" in out
    assert [call.args[1] for call in reconcile.call_args_list] == ["account:acct1", "account:acct2"]
    assert conn.closed is True


def test_main_warns_about_unreported_orders(monkeypatch, capsys) -> None:
    """Orders the broker stopped reporting must be surfaced, not swallowed.

    They are left open on purpose — see open_order_reconciliation's module
    docstring — so the warning is the only thing standing between the operator
    and a row that silently sits at `submitted` forever.
    """
    conn = FakeConn()
    install_args(monkeypatch, "acct1")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    monkeypatch.setattr(
        module,
        "reconcile_open_orders",
        Mock(return_value=ReconciliationOutcome(newly_filled=0, unreported_broker_order_ids=["ib-7", "ib-9"])),
    )

    module.main()

    captured = capsys.readouterr()
    assert "acct1: reconciled 0 newly filled order(s)" in captured.out
    assert "2 open order(s) not reported by the broker" in captured.err
    assert "ib-7, ib-9" in captured.err


def test_main_stays_quiet_when_every_order_is_accounted_for(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_args(monkeypatch, "acct1")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    monkeypatch.setattr(module, "reconcile_open_orders", Mock(return_value=ReconciliationOutcome()))

    module.main()

    assert capsys.readouterr().err == ""


def test_main_skips_blank_account_names(monkeypatch, capsys) -> None:
    conn = FakeConn()
    install_args(monkeypatch, " acct1 , , ")
    monkeypatch.setattr(init_module, "ensure_db", lambda: conn)
    monkeypatch.setattr(module, "get_account", lambda _conn, name: f"account:{name}")
    reconcile = Mock(return_value=ReconciliationOutcome())
    monkeypatch.setattr(module, "reconcile_open_orders", reconcile)

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
        "reconcile_open_orders",
        Mock(side_effect=RuntimeError("broker unreachable")),
    )

    with pytest.raises(RuntimeError, match="broker unreachable"):
        module.main()

    assert conn.closed is True
