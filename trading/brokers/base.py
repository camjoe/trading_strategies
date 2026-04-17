"""Broker interface — abstract contract for order submission and account queries.

All broker adapters must implement :class:`BrokerConnection`.  Concrete adapters
are injected at the runtime / interface layer.

Order data types live in :mod:`trading.models.broker_order` so that repositories
and services can use them without depending on this package.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from trading.models.broker_order import (  # noqa: F401 — re-exported for broker adapters
    BrokerOrder,
    OrderFill,
    OrderStatus,
    OrderType,
    TimeInForce,
)


class BrokerConnection(ABC):
    """Abstract interface over a broker connection.

    Implement this class to add a new broker.  Register the adapter in
    :func:`trading.brokers.factory.get_broker_for_account`.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the broker endpoint."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection gracefully."""

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrder:
        """Submit *order* and return it populated with broker-assigned fields.

        For synchronous/paper brokers the returned order will have
        ``status == OrderStatus.FILLED``.  For async live brokers the status
        will be ``SUBMITTED`` initially and updated via separate fill events.
        """

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        """Request cancellation of an open order."""

    @abstractmethod
    def get_open_trades(self) -> list[BrokerOrder]:
        """Return currently open broker orders with their latest known fill state."""

    @abstractmethod
    def get_positions(self) -> dict[str, float]:
        """Return current live positions as ``{ticker: qty}``."""

    @abstractmethod
    def get_account_info(self) -> dict[str, float]:
        """Return account summary: ``cash``, ``buying_power``, ``market_value``, etc."""

    @abstractmethod
    def get_quotes(self, tickers: list[str]) -> dict[str, dict[str, float]]:
        """Return real-time quotes for *tickers* as ``{ticker: {bid, ask, last}}``."""
