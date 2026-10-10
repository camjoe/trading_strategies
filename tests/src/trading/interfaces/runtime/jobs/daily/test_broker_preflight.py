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
from infrastructure.brokers.ibkr_web.client import IbWebAccountUnavailableError
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

    assert module.check_broker_sessions(["acct_a", "acct_b"]) == {}

    assert set(brokers) == {"acct_a", "acct_b"}
    assert all(broker.disconnected for broker in brokers.values())


def test_an_unauthenticated_session_is_reported_and_the_rest_still_connect(monkeypatch) -> None:
    brokers = install(
        monkeypatch,
        {"acct_a": None, "acct_b": RuntimeError("IBKR Web API session is not authenticated.")},
    )

    unavailable = module.check_broker_sessions(["acct_a", "acct_b"])

    assert unavailable == {"acct_b": "interactive_brokers_web_paper: IBKR Web API session is not authenticated."}
    assert brokers["acct_a"].disconnected


def test_an_unreachable_gateway_fails_when_every_account_is_down(monkeypatch) -> None:
    refused = httpx.ConnectError("[Errno 111] Connection refused")
    install(monkeypatch, {"acct_a": refused, "acct_b": refused})

    with pytest.raises(module.BrokerSessionUnavailableError) as raised:
        module.check_broker_sessions(["acct_a", "acct_b"])

    assert set(raised.value.unavailable) == {"acct_a", "acct_b"}
    assert "Connection refused" in raised.value.unavailable["acct_a"]


def test_a_repeated_account_name_does_not_hide_that_every_account_is_down(monkeypatch) -> None:
    install(monkeypatch, {"acct_a": httpx.ConnectError("refused")})

    with pytest.raises(module.BrokerSessionUnavailableError):
        module.check_broker_sessions(["acct_a", "acct_a"])


def test_a_socket_gateway_that_times_out_is_reported_not_raised(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": TimeoutError("Timed out waiting for IBKR native nextValidId callback"), "acct_b": None},
    )

    unavailable = module.check_broker_sessions(["acct_a", "acct_b"])

    assert "nextValidId" in unavailable["acct_a"]


def test_an_account_the_session_cannot_see_stops_the_run(monkeypatch) -> None:
    error = IbWebAccountUnavailableError("account_id 'DU1' is not visible in the current session.")
    install(monkeypatch, {"acct_a": error})

    with pytest.raises(IbWebAccountUnavailableError):
        module.check_broker_sessions(["acct_a"])


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


def test_the_failure_text_names_each_account_and_the_runbook(monkeypatch) -> None:
    install(monkeypatch, {"acct_a": httpx.ConnectError("gateway down")})

    with pytest.raises(module.BrokerSessionUnavailableError) as raised:
        module.check_broker_sessions(["acct_a"])

    message = str(raised.value)
    assert "acct_a (interactive_brokers_web_paper: gateway down)" in message
    assert "docs/runbooks/ibkr-paper-trading.md" in message
