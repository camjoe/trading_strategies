from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

import infrastructure.database.connection as init_module
from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    PaperBrokerAccountMismatchError,
    UnknownBrokerTypeError,
)
from tests.src.trading.interfaces.runtime.jobs.loaders import load_runtime_job

BROKER_PREFLIGHT_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading.broker_preflight"
module = load_runtime_job(BROKER_PREFLIGHT_MODULE)


class FakeConn:
    def close(self) -> None:
        pass


class FakeBroker:
    def __init__(self) -> None:
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


def install(monkeypatch, outcomes: dict[str, object]) -> dict[str, FakeBroker]:
    """Route each account name to a broker, or raise when its outcome is an exception."""
    brokers: dict[str, FakeBroker] = {}

    def factory(account):
        outcome = outcomes[account.name]
        if isinstance(outcome, Exception):
            raise outcome
        brokers[account.name] = FakeBroker()
        return brokers[account.name]

    monkeypatch.setattr(init_module, "ensure_db", lambda: FakeConn())
    monkeypatch.setattr(
        module,
        "get_account",
        lambda _conn, name: SimpleNamespace(name=name, broker_type="interactive_brokers_web_paper"),
    )
    monkeypatch.setattr(module, "get_broker_for_account", factory)
    return brokers


def test_connects_and_disconnects_every_account(monkeypatch) -> None:
    brokers = install(monkeypatch, {"acct_a": None, "acct_b": None})

    module.check_broker_sessions(["acct_a", "acct_b"])

    assert set(brokers) == {"acct_a", "acct_b"}
    assert all(broker.disconnected for broker in brokers.values())


def test_unauthenticated_session_names_the_account_and_the_runbook(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": None, "acct_b": RuntimeError("IBKR Web API session is not authenticated.")},
    )

    with pytest.raises(module.BrokerSessionUnavailableError) as raised:
        module.check_broker_sessions(["acct_a", "acct_b"])

    message = str(raised.value)
    assert "acct_b (interactive_brokers_web_paper): IBKR Web API session is not authenticated." in message
    assert "acct_a" not in message
    assert "docs/runbooks/ibkr-paper-trading.md" in message


def test_unreachable_gateway_reports_every_failing_account(monkeypatch) -> None:
    refused = httpx.ConnectError("[Errno 111] Connection refused")
    install(monkeypatch, {"acct_a": refused, "acct_b": refused})

    with pytest.raises(module.BrokerSessionUnavailableError) as raised:
        module.check_broker_sessions(["acct_a", "acct_b"])

    message = str(raised.value)
    assert "acct_a" in message
    assert "acct_b" in message
    assert "Connection refused" in message


@pytest.mark.parametrize(
    "guard_error",
    [
        LiveTradingNotEnabledError("live gate"),
        PaperBrokerAccountMismatchError("not a paper account"),
        UnknownBrokerTypeError("unknown broker"),
    ],
)
def test_broker_guard_errors_propagate_unchanged(monkeypatch, guard_error: RuntimeError) -> None:
    install(monkeypatch, {"acct_a": guard_error})

    with pytest.raises(type(guard_error)) as raised:
        module.check_broker_sessions(["acct_a"])

    assert raised.value is guard_error
