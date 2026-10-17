"""BrokerSession holds socket connections across leases and replaces dropped ones."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrastructure.brokers.ibkr_socket.adapter import IbkrSocketAdapter
from infrastructure.brokers.paper_adapter import PaperBrokerAdapter
from infrastructure.brokers.session import BrokerSession
from tests.support.account_records import make_account_record
from trading.models.orders import OrderRequest


def _socket_adapter(*, connected: bool = True) -> tuple[IbkrSocketAdapter, MagicMock]:
    client = MagicMock()
    client.is_connected.return_value = connected
    return IbkrSocketAdapter(client=client, host="127.0.0.1", port=4002, client_id=7), client


class _Connector:
    """Hands out the next scripted broker and records which account asked."""

    def __init__(self, *brokers) -> None:
        self._brokers = list(brokers)
        self.requested: list[int] = []

    def __call__(self, account):
        self.requested.append(account["id"])
        return self._brokers.pop(0)


def test_a_second_lease_reuses_the_held_connection() -> None:
    adapter, client = _socket_adapter()
    connector = _Connector(adapter)
    session = BrokerSession(connect=connector)
    account = make_account_record(id=1)

    first = session.lease(account)
    second = session.lease(account)

    assert connector.requested == [1]
    first.get_positions()
    second.get_positions()
    assert client.positions.call_count == 2


def test_the_lease_disconnect_leaves_the_connection_open() -> None:
    adapter, client = _socket_adapter()
    session = BrokerSession(connect=_Connector(adapter))

    lease = session.lease(make_account_record(id=1))
    lease.disconnect()
    lease.connect()

    client.disconnect.assert_not_called()
    client.connect.assert_not_called()


def test_close_disconnects_every_held_connection() -> None:
    first, first_client = _socket_adapter()
    second, second_client = _socket_adapter()
    session = BrokerSession(connect=_Connector(first, second))
    session.lease(make_account_record(id=1))
    session.lease(make_account_record(id=2))

    session.close()

    first_client.disconnect.assert_called_once_with()
    second_client.disconnect.assert_called_once_with()


def test_a_dropped_connection_is_replaced_on_the_next_lease() -> None:
    dropped, dropped_client = _socket_adapter()
    replacement, replacement_client = _socket_adapter()
    connector = _Connector(dropped, replacement)
    session = BrokerSession(connect=connector)
    account = make_account_record(id=1)
    session.lease(account)
    dropped_client.is_connected.return_value = False

    lease = session.lease(account)
    lease.get_positions()

    assert connector.requested == [1, 1]
    dropped_client.positions.assert_not_called()
    replacement_client.positions.assert_called_once_with()


def test_each_account_holds_its_own_connection() -> None:
    first, first_client = _socket_adapter()
    second, second_client = _socket_adapter()
    session = BrokerSession(connect=_Connector(first, second))

    session.lease(make_account_record(id=1)).get_positions()
    session.lease(make_account_record(id=2)).get_positions()

    first_client.positions.assert_called_once_with()
    second_client.positions.assert_called_once_with()


def test_a_broker_that_is_not_a_socket_adapter_is_returned_unwrapped() -> None:
    simulator = PaperBrokerAdapter()
    connector = _Connector(simulator, PaperBrokerAdapter())
    session = BrokerSession(connect=connector)
    account = make_account_record(id=1)

    assert session.lease(account) is simulator
    session.lease(account)

    assert connector.requested == [1, 1]


def test_a_failed_connect_propagates_and_holds_nothing() -> None:
    def refuse(_account):
        raise ConnectionRefusedError("refused")

    session = BrokerSession(connect=refuse)

    with pytest.raises(ConnectionRefusedError):
        session.lease(make_account_record(id=1))
    session.close()


def test_close_continues_past_a_connection_that_fails_to_disconnect() -> None:
    first, first_client = _socket_adapter()
    second, second_client = _socket_adapter()
    first_client.disconnect.side_effect = OSError("broken pipe")
    session = BrokerSession(connect=_Connector(first, second))
    session.lease(make_account_record(id=1))
    session.lease(make_account_record(id=2))

    session.close()

    second_client.disconnect.assert_called_once_with()


def test_the_session_closes_on_leaving_its_context() -> None:
    adapter, client = _socket_adapter()

    with BrokerSession(connect=_Connector(adapter)) as session:
        session.lease(make_account_record(id=1))

    client.disconnect.assert_called_once_with()


def test_the_lease_forwards_every_broker_call_and_the_execution_flag() -> None:
    held = MagicMock(spec=IbkrSocketAdapter)
    held.reports_executions = False
    held.is_connected.return_value = True
    lease = BrokerSession(connect=lambda _account: held).lease(make_account_record(id=1))
    order = OrderRequest(account_id=1, ticker="AAPL", side="buy", qty=1.0, price=1.0)

    lease.place_order(order)
    lease.cancel_order("5")
    lease.get_open_trades()
    lease.get_order("5")
    lease.get_positions()
    lease.get_account_info()
    lease.get_quotes(["AAPL"])

    held.place_order.assert_called_once_with(order)
    held.cancel_order.assert_called_once_with("5")
    held.get_open_trades.assert_called_once_with()
    held.get_order.assert_called_once_with("5")
    held.get_positions.assert_called_once_with()
    held.get_account_info.assert_called_once_with()
    held.get_quotes.assert_called_once_with(["AAPL"])
    assert lease.reports_executions is False
