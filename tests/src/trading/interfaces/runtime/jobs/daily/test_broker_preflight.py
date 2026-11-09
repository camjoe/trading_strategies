from __future__ import annotations

from decimal import Decimal
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


WEB_PAPER = "interactive_brokers_web_paper"
SOCKET_PAPER = "interactive_brokers_socket_paper"
ACCOUNTS: dict[str, SimpleNamespace] = {}


def account(name: str, broker_type: str, host: str | None = None, port: int | None = None) -> None:
    ACCOUNTS[name] = SimpleNamespace(name=name, broker_type=broker_type, broker_host=host, broker_port=port)


@pytest.fixture(autouse=True)
def _reset_accounts():
    ACCOUNTS.clear()
    yield
    ACCOUNTS.clear()


class FakeConn:
    def close(self) -> None:
        pass


class FakeBroker:
    """A broker session; ``info`` None behaves like the simulator, which has no account summary."""

    def __init__(self, info: dict[str, float] | None = None) -> None:
        self.info = info
        self.disconnected = False

    def get_account_info(self) -> dict[str, float]:
        if self.info is None:
            raise NotImplementedError("simulator keeps cash in the books")
        return self.info

    def disconnect(self) -> None:
        self.disconnected = True


def install(
    monkeypatch,
    outcomes: dict[str, object],
    book_cash: dict[str, Decimal] | None = None,
) -> dict[str, FakeBroker]:
    """Route each account name to a broker, or raise when its outcome is an exception.

    An outcome that is a ``FakeBroker`` is used as given; ``book_cash`` is what the books hold per broker type.
    """
    brokers: dict[str, FakeBroker] = {}

    def factory(account):
        outcome = outcomes[account.name]
        if isinstance(outcome, Exception):
            raise outcome
        brokers[account.name] = outcome if isinstance(outcome, FakeBroker) else FakeBroker()
        return brokers[account.name]

    monkeypatch.setattr(init_module, "ensure_db", lambda: FakeConn())
    monkeypatch.setattr(
        module,
        "get_account",
        lambda _conn, name: (
            ACCOUNTS.get(name) or SimpleNamespace(name=name, broker_type=WEB_PAPER, broker_host=None, broker_port=None)
        ),
    )
    monkeypatch.setattr(module, "get_broker_for_account", factory)
    monkeypatch.setattr(module, "fetch_book_cash_by_pool", lambda _conn: book_cash or {})
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


def test_books_holding_more_than_the_broker_skip_every_account_in_the_pool(monkeypatch) -> None:
    brokers = install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 70_000.0}), "acct_b": FakeBroker({"TotalCashValue": 70_000.0})},
        book_cash={"ibkr_web": Decimal("80000.00")},
    )

    with pytest.raises(module.BrokerCashShortfallError) as raised:
        module.check_broker_cash(["acct_a", "acct_b"], already_skipped={})

    assert set(raised.value.skipped) == {"acct_a", "acct_b"}
    assert "the books hold 80000.00 cash and the broker holds 70000.00" in raised.value.skipped["acct_a"]
    assert "docs/runbooks/ibkr-paper-trading.md" in str(raised.value)
    assert [name for name, broker in brokers.items() if broker.disconnected] == ["acct_a"]


def test_the_cash_is_read_once_per_pool(monkeypatch) -> None:
    brokers = install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 100.0}), "acct_b": FakeBroker({"TotalCashValue": 5.0})},
        book_cash={"ibkr_web": Decimal("50.00")},
    )

    assert module.check_broker_cash(["acct_a", "acct_b"], already_skipped={}) == {}
    assert set(brokers) == {"acct_a"}


def test_a_shortfall_skips_the_pool_and_leaves_the_simulator_accounts_alone(monkeypatch) -> None:
    account("sim", "paper")
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 70_000.0}), "sim": None},
        book_cash={"ibkr_web": Decimal("80000.00")},
    )

    skipped = module.check_broker_cash(["acct_a", "sim"], already_skipped={})

    assert set(skipped) == {"acct_a"}


def test_books_within_the_broker_cash_are_not_skipped(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 80_000.0})},
        book_cash={"ibkr_web": Decimal("80000.50")},
    )

    assert module.check_broker_cash(["acct_a"], already_skipped={}) == {}


def test_a_shortfall_just_over_the_tolerance_is_skipped(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 80_000.0})},
        book_cash={"ibkr_web": Decimal("80001.01")},
    )

    with pytest.raises(module.BrokerCashShortfallError):
        module.check_broker_cash(["acct_a"], already_skipped={})


def test_books_of_accounts_outside_the_run_count_against_the_shared_cash(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 30_000.0})},
        book_cash={"ibkr_web": Decimal("90000.00")},
    )

    with pytest.raises(module.BrokerCashShortfallError):
        module.check_broker_cash(["acct_a"], already_skipped={})


@pytest.mark.parametrize(
    "info",
    [{"NetLiquidation": 1.0}, {"TotalCashValue": float("nan")}, {"TotalCashValue": float("inf")}],
)
def test_an_answer_without_a_usable_cash_figure_skips_the_pool_with_the_reason(monkeypatch, info) -> None:
    brokers = install(
        monkeypatch,
        {"acct_a": FakeBroker(info), "acct_b": FakeBroker({"TotalCashValue": 1.0})},
        book_cash={"ibkr_web": Decimal("10.00")},
    )

    with pytest.raises(module.BrokerCashShortfallError) as raised:
        module.check_broker_cash(["acct_a", "acct_b"], already_skipped={})

    assert "could not read the broker's cash" in raised.value.skipped["acct_b"]
    assert brokers["acct_a"].disconnected


def test_a_cash_read_that_fails_to_parse_is_a_skip_not_a_crash(monkeypatch) -> None:
    class Garbled(FakeBroker):
        def get_account_info(self) -> dict[str, float]:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    account("sim", "paper")
    install(monkeypatch, {"acct_a": Garbled(), "sim": None}, book_cash={"ibkr_web": Decimal("10.00")})

    skipped = module.check_broker_cash(["acct_a", "sim"], already_skipped={})

    assert set(skipped) == {"acct_a"}
    assert "Expecting value" in skipped["acct_a"]


def test_a_failed_read_still_disconnects(monkeypatch) -> None:
    account("sim", "paper")
    broker = FakeBroker({"NetLiquidation": 1.0})
    install(monkeypatch, {"acct_a": broker, "sim": None}, book_cash={"ibkr_web": Decimal("10.00")})

    module.check_broker_cash(["acct_a", "sim"], already_skipped={})

    assert broker.disconnected


def test_socket_accounts_on_different_ports_are_different_pools(monkeypatch) -> None:
    account("acct_a", SOCKET_PAPER, "127.0.0.1", 4002)
    account("acct_b", SOCKET_PAPER, "127.0.0.1", 4003)
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 50_000.0}), "acct_b": FakeBroker({"TotalCashValue": 50_000.0})},
        book_cash={
            "ibkr_socket:127.0.0.1:4002": Decimal("50000.00"),
            "ibkr_socket:127.0.0.1:4003": Decimal("50000.00"),
        },
    )

    assert module.check_broker_cash(["acct_a", "acct_b"], already_skipped={}) == {}


def test_the_error_names_every_skipped_account_when_a_session_was_down_earlier(monkeypatch) -> None:
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 1.0})},
        book_cash={"ibkr_web": Decimal("100.00")},
    )

    with pytest.raises(module.BrokerCashShortfallError) as raised:
        module.check_broker_cash(["acct_a"], already_skipped={"acct_z": f"{WEB_PAPER}: gateway down"})

    assert set(raised.value.skipped) == {"acct_a", "acct_z"}


def test_one_account_left_means_the_run_goes_on_with_it(monkeypatch) -> None:
    account("sim", "paper")
    install(
        monkeypatch,
        {"acct_a": FakeBroker({"TotalCashValue": 1.0}), "sim": None},
        book_cash={"ibkr_web": Decimal("100.00")},
    )

    assert set(module.check_broker_cash(["acct_a", "sim"], already_skipped={})) == {"acct_a"}


def test_broker_guard_errors_propagate_from_the_cash_check(monkeypatch) -> None:
    guard = PaperBrokerAccountMismatchError("not a paper account")
    install(monkeypatch, {"acct_a": guard}, book_cash={"ibkr_web": Decimal("1.00")})

    with pytest.raises(PaperBrokerAccountMismatchError) as raised:
        module.check_broker_cash(["acct_a"], already_skipped={})

    assert raised.value is guard


def test_a_simulator_only_run_reads_no_cash(monkeypatch) -> None:
    account("sim", "paper")
    brokers = install(monkeypatch, {"sim": None}, book_cash={"ibkr_web": Decimal("10.00")})

    assert module.check_broker_cash(["sim"], already_skipped={}) == {}
    assert brokers == {}
