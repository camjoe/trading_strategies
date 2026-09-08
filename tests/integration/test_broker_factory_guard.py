"""Integration test for the broker abstraction and the live-trading guard.

Covers the core capability "broker abstraction" from ``docs/overview.md``:
service and domain code depend only on the ``BrokerConnection`` port, and the
factory is the sole place broker routing and the ``live_trading_enabled`` guard
live. The test checks the three routing outcomes that matter for safety —
paper resolves, a live transport without the guard is refused, and an unknown
type fails loudly rather than falling through to the simulator.
"""

from __future__ import annotations

import pytest

from infrastructure.brokers.factory import (
    LiveTradingNotEnabledError,
    UnknownBrokerTypeError,
    get_broker_for_account,
)
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from tests.support.account_records import make_account_record


def test_paper_account_resolves_to_the_simulator() -> None:
    account = make_account_record(broker_type="paper", live_trading_enabled=0)
    broker = get_broker_for_account(account)
    assert isinstance(broker, PaperBrokerAdapter)


def test_live_web_transport_is_refused_without_the_guard() -> None:
    account = make_account_record(broker_type="interactive_brokers_web", live_trading_enabled=0)
    with pytest.raises(LiveTradingNotEnabledError):
        get_broker_for_account(account)


def test_unknown_broker_type_fails_loudly() -> None:
    account = make_account_record(broker_type="totally_made_up", live_trading_enabled=0)
    with pytest.raises(UnknownBrokerTypeError):
        get_broker_for_account(account)
