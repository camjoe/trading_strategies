"""Tests for trading.domain.broker_cash."""

from __future__ import annotations

from decimal import Decimal

import pytest

from trading.domain.broker_cash import BROKER_CASH_TOLERANCE, broker_cash_pool, broker_cash_shortfall


@pytest.mark.parametrize(
    ("book_cash", "broker_cash", "expected"),
    [
        (Decimal("80000.00"), 70000.0, Decimal("9999.00")),
        (Decimal("70000.00"), 70000.0, Decimal(0)),
        (Decimal("60000.00"), 70000.0, Decimal(0)),
        (Decimal("70000.00") + BROKER_CASH_TOLERANCE, 70000.0, Decimal(0)),
        (Decimal("70001.01"), 70000.0, Decimal("0.01")),
        (Decimal("10.00"), 0.0, Decimal("9.00")),
    ],
)
def test_shortfall_is_the_excess_beyond_the_tolerance(
    book_cash: Decimal, broker_cash: float, expected: Decimal
) -> None:
    assert broker_cash_shortfall(book_cash, broker_cash) == expected


@pytest.mark.parametrize("broker_type", ["interactive_brokers_web", "interactive_brokers_web_paper"])
def test_every_web_account_shares_one_pool_whatever_its_host_and_port(broker_type: str) -> None:
    assert broker_cash_pool(broker_type, None, None) == "ibkr_web"
    assert broker_cash_pool(broker_type, "10.0.0.5", 5000) == "ibkr_web"


def test_socket_accounts_share_a_pool_only_when_host_and_port_match() -> None:
    first = broker_cash_pool("interactive_brokers_socket_paper", "127.0.0.1", 4002)

    assert first == broker_cash_pool("interactive_brokers_socket", "127.0.0.1", 4002)
    assert first != broker_cash_pool("interactive_brokers_socket_paper", "127.0.0.1", 4003)
    assert first != broker_cash_pool("interactive_brokers_socket_paper", "10.0.0.5", 4002)


def test_socket_accounts_with_no_host_and_port_share_the_default_pool() -> None:
    assert broker_cash_pool("interactive_brokers_socket_paper", None, None) == broker_cash_pool(
        "interactive_brokers_socket", None, None
    )


@pytest.mark.parametrize("broker_type", ["paper", None, ""])
def test_an_account_whose_broker_keeps_no_cash_has_no_pool(broker_type: str | None) -> None:
    assert broker_cash_pool(broker_type, None, None) is None


def test_the_broker_type_is_read_trimmed_and_lower_cased_as_the_factory_reads_it() -> None:
    assert broker_cash_pool(" Interactive_Brokers_Web_Paper ", None, None) == "ibkr_web"
