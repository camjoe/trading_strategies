"""Hold one IBKR socket connection per account across several phases of a long-running process.

No job uses this yet: every daily phase still connects through ``get_broker_for_account`` and disconnects.

``get_broker_for_account`` connects on every call and callers disconnect in a ``finally``. A
:class:`BrokerSession` is passed in its place as ``broker_factory``: the first lease for an account
connects through the factory, later leases reuse that connection, and the lease's ``disconnect()``
does nothing. The owner calls :meth:`BrokerSession.close` once, at shutdown.

The factory's guards (``live_trading_enabled``, the paper-account assertion) run only when it connects,
so a held connection is kept only while the account row's broker settings and ``live_trading_enabled``
match those it connected with. A lease with a changed row disconnects the held connection and connects
again through the factory, which raises if a guard no longer passes. Pass the row freshly read from the
database to every lease.

A dropped connection is replaced on the next lease the same way. A lease taken before the connection was
replaced, or after :meth:`BrokerSession.close`, raises ``RuntimeError`` on every call. A call that fails
because the connection dropped mid-use raises as it would without a session; the session does not retry
it. Not thread-safe.

Only socket adapters are held. Any other broker (the simulator, the Web API adapter) is returned
unwrapped, so the caller's ``disconnect()`` closes it as before.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
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
    """A held broker that ignores ``connect`` and ``disconnect``; everything else is forwarded.

    Every forwarded call first checks that the connection it was taken from is still the session's.
    """

    def __init__(self, held: BrokerConnection, is_current: Callable[[], bool]) -> None:
        self._held = held
        self._is_current = is_current
        self.reports_executions = held.reports_executions

    def _broker(self) -> BrokerConnection:
        if not self._is_current():
            raise RuntimeError("This IBKR lease is stale: its connection was replaced or the session was closed.")
        return self._held

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def place_order(self, order: OrderRequest) -> BrokerOrder:
        return self._broker().place_order(order)

    def cancel_order(self, broker_order_id: str) -> None:
        self._broker().cancel_order(broker_order_id)

    def get_open_trades(self) -> list[BrokerOrder]:
        return self._broker().get_open_trades()

    def get_order(self, broker_order_id: str) -> BrokerOrder | None:
        return self._broker().get_order(broker_order_id)

    def get_positions(self) -> dict[str, float]:
        return self._broker().get_positions()

    def get_account_info(self) -> dict[str, float]:
        return self._broker().get_account_info()

    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        return self._broker().get_quotes(tickers)


@dataclass(frozen=True)
class _Held:
    adapter: IbkrSocketAdapter
    # What the guards were evaluated against when this connection was made.
    settings: tuple[object, ...]


def _broker_settings(account: AccountRecord) -> tuple[object, ...]:
    return (
        account.broker_type,
        account.broker_host,
        account.broker_port,
        account.broker_client_id,
        bool(account.live_trading_enabled),
    )


class BrokerSession:
    """Lease held socket connections, one per account, reconnecting any that dropped or went stale."""

    def __init__(self, connect: Callable[[AccountRecord], BrokerConnection] = get_broker_for_account) -> None:
        self._connect = connect
        self._held: dict[int, _Held] = {}
        self._closed = False

    def lease(self, account: AccountRecord) -> BrokerConnection:
        """Return a connected broker for *account*, in the shape of ``broker_factory``."""
        if self._closed:
            raise RuntimeError("This BrokerSession is closed.")
        account_id = row_expect_int(account, "id")
        settings = _broker_settings(account)
        held = self._held.get(account_id)
        if held is not None:
            if held.settings == settings and held.adapter.is_connected():
                return self._lease_of(account_id, held)
            reason = "its broker settings changed" if held.settings != settings else "it dropped"
            logger.warning("IBKR socket connection for account %s released because %s.", account_id, reason)
            self._release(account_id)

        broker = self._connect(account)
        if not isinstance(broker, IbkrSocketAdapter):
            return broker
        held = _Held(adapter=broker, settings=settings)
        self._held[account_id] = held
        return self._lease_of(account_id, held)

    def close(self) -> None:
        """Disconnect every held connection and refuse further leases. A failure on one does not stop the others."""
        self._closed = True
        for account_id in list(self._held):
            self._release(account_id)

    def _lease_of(self, account_id: int, held: _Held) -> _BrokerLease:
        return _BrokerLease(held.adapter, lambda: self._held.get(account_id) is held)

    def _release(self, account_id: int) -> None:
        adapter = self._held.pop(account_id).adapter
        try:
            adapter.abandon()
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
