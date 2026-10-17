"""Hold one IBKR socket connection per account across several phases of a long-running process.

``get_broker_for_account`` connects on every call and callers disconnect in a ``finally``. A
:class:`BrokerSession` is passed in its place as ``broker_factory``: the first lease for an account
connects through the factory, later leases reuse that connection, and the lease's ``disconnect()``
does nothing. The owner calls :meth:`BrokerSession.close` once, at shutdown.

A dropped connection is replaced on the next lease through the same factory, so the connect retry and
the paper-account assertion run again. A call that fails because the connection dropped mid-use raises
as it would without a session; the session does not retry it. Not thread-safe.

Only socket adapters are held. Any other broker (the simulator, the Web API adapter) is returned
unwrapped, so the caller's ``disconnect()`` closes it as before.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import TracebackType

from common.coercion import row_expect_int
from infrastructure.brokers.factory import get_broker_for_account
from infrastructure.brokers.ibkr_socket.adapter import IbkrSocketAdapter
from trading.domain.broker_connection import BrokerConnection
from trading.models import AccountRecord
from trading.models.orders import BrokerOrder, OrderRequest

__all__ = ["BrokerSession"]

logger = logging.getLogger(__name__)


class _BrokerLease(BrokerConnection):
    """A held broker that ignores ``connect`` and ``disconnect``; everything else is forwarded."""

    def __init__(self, held: BrokerConnection) -> None:
        self._held = held
        self.reports_executions = held.reports_executions

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        return self._held.place_order(order)

    def cancel_order(self, broker_order_id: str) -> None:
        self._held.cancel_order(broker_order_id)

    def get_open_trades(self) -> list[BrokerOrder]:
        return self._held.get_open_trades()

    def get_order(self, broker_order_id: str) -> BrokerOrder | None:
        return self._held.get_order(broker_order_id)

    def get_positions(self) -> dict[str, float]:
        return self._held.get_positions()

    def get_account_info(self) -> dict[str, float]:
        return self._held.get_account_info()

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        return self._held.get_quotes(tickers)


class BrokerSession:
    """Lease held socket connections, one per account, reconnecting any that dropped."""

    def __init__(self, connect: Callable[[AccountRecord], BrokerConnection] = get_broker_for_account) -> None:
        self._connect = connect
        self._held: dict[int, IbkrSocketAdapter] = {}

    def lease(self, account: AccountRecord) -> BrokerConnection:
        """Return a connected broker for *account*, in the shape of ``broker_factory``."""
        account_id = row_expect_int(account, "id")
        held = self._held.get(account_id)
        if held is not None and held.is_connected():
            return _BrokerLease(held)
        if held is not None:
            logger.warning("IBKR socket connection for account %s dropped; reconnecting.", account_id)
            self._release(account_id)

        broker = self._connect(account)
        if not isinstance(broker, IbkrSocketAdapter):
            return broker
        self._held[account_id] = broker
        return _BrokerLease(broker)

    def close(self) -> None:
        """Disconnect every held connection. A failure on one does not stop the others."""
        for account_id in list(self._held):
            self._release(account_id)

    def _release(self, account_id: int) -> None:
        held = self._held.pop(account_id)
        try:
            held.disconnect()
        except Exception:
            logger.warning("Disconnecting the IBKR socket for account %s failed.", account_id, exc_info=True)

    def __enter__(self) -> BrokerSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
