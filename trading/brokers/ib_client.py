"""IB client abstraction — decouples InteractiveBrokersAdapter from any specific library.

Two concrete clients are provided:

  IbAsyncClient   — wraps ``ib_async`` (the actively maintained community fork of ib_insync).
                    This is the default and recommended client.

  IbApiClient     — wraps IBKR's official native ``ibapi`` package (callback-based).
                    Documented stub; implement when you prefer zero third-party dependencies.

The factory decides which client to inject.  To switch backends, change
``IB_CLIENT_BACKEND`` in ``trading/brokers/factory.py`` — no other code needs to change.

Protocol contract
-----------------
Any custom client must implement :class:`IBClientProtocol`.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IBClientProtocol(Protocol):
    """Minimal interface that any IB client backend must satisfy.

    ``InteractiveBrokersAdapter`` depends only on this protocol — not on
    ``ib_async``, ``ibapi``, or any other concrete library.
    """

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        """Establish connection to TWS/IB Gateway."""
        ...

    def disconnect(self) -> None:
        """Close the connection gracefully."""
        ...

    def is_connected(self) -> bool:
        """Return True if currently connected."""
        ...

    def place_order(self, contract: Any, order: Any) -> Any:
        """Submit an order and return the trade object."""
        ...

    def cancel_order(self, order: Any) -> None:
        """Request cancellation of an open order."""
        ...

    def trades(self) -> list[Any]:
        """Return all currently tracked trade objects."""
        ...

    def positions(self) -> list[Any]:
        """Return all account positions."""
        ...

    def account_summary(self) -> list[Any]:
        """Return account summary value objects."""
        ...

    def make_stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Any:
        """Create a Stock contract for the given symbol."""
        ...

    def make_order(self, **kwargs: Any) -> Any:
        """Create a broker order object with the given parameters."""
        ...

    def qualify_contracts(self, *contracts: Any) -> list[Any]:
        """Qualify contracts by fetching full details from IB."""
        ...

    def req_tickers(self, *contracts: Any) -> list[Any]:
        """Request real-time ticker snapshots for contracts."""
        ...


# ---------------------------------------------------------------------------
# IbAsyncClient — wraps ib_async (recommended)
# ---------------------------------------------------------------------------


class IbAsyncClient:
    """IBClientProtocol implementation backed by ``ib_async``.

    ``ib_async`` is the actively maintained community fork of ``ib_insync``
    (https://github.com/ib-api-reloaded/ib_async).  Install with:
        pip install ib_async

    The API is a near drop-in replacement for ``ib_insync``.
    """

    def __init__(self) -> None:
        import ib_async  # noqa: PLC0415

        self._ib = ib_async.IB()

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        self._ib.connect(host, port, clientId=client_id)

    def disconnect(self) -> None:
        self._ib.disconnect()

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    def place_order(self, contract: Any, order: Any) -> Any:
        return self._ib.placeOrder(contract, order)

    def cancel_order(self, order: Any) -> None:
        self._ib.cancelOrder(order)

    def trades(self) -> list[Any]:
        return self._ib.trades()

    def positions(self) -> list[Any]:
        return self._ib.positions()

    def account_summary(self) -> list[Any]:
        return self._ib.accountSummary()

    def qualify_contracts(self, *contracts: Any) -> list[Any]:
        return self._ib.qualifyContracts(*contracts)

    def req_tickers(self, *contracts: Any) -> list[Any]:
        return self._ib.reqTickers(*contracts)

    def make_stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Any:
        import ib_async  # noqa: PLC0415

        return ib_async.Stock(symbol, exchange, currency)

    def make_order(self, **kwargs: Any) -> Any:
        import ib_async  # noqa: PLC0415

        return ib_async.Order(**kwargs)


# ---------------------------------------------------------------------------
# IbApiClient — wraps IBKR native ibapi (stub)
# ---------------------------------------------------------------------------


class IbApiClient:
    """IBClientProtocol implementation backed by IBKR's official ``ibapi`` package.

    This is a documented stub for teams that prefer zero third-party dependencies
    and are willing to work with ibapi's callback-based architecture directly.

    Install the native API:
        pip install ibapi
      or download from https://interactivebrokers.github.io/

    Implementation notes
    --------------------
    ``ibapi`` is callback-based (EWrapper + EClient).  To implement this client:

    1. Subclass both ``ibapi.wrapper.EWrapper`` and ``ibapi.client.EClient``.
    2. Implement callback methods (``execDetails``, ``orderStatus``, ``position``,
       ``accountSummaryEnd``, etc.) to collect results into threading.Event/Queue.
    3. Wrap each operation in a synchronous helper that fires the request and
       blocks on the corresponding Event/Queue until the callback fires.

    Example skeleton::

        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        import threading

        class _IBApp(EWrapper, EClient):
            def __init__(self):
                EWrapper.__init__(self)
                EClient.__init__(self, self)
                self._positions: list = []
                self._pos_event = threading.Event()

            def position(self, account, contract, pos, avg_cost):
                self._positions.append((contract.symbol, pos))

            def positionEnd(self):
                self._pos_event.set()

    Then ``IbApiClient.connect()`` would spin the app in a background thread and
    each public method would trigger the appropriate request + wait on its Event.
    """

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        raise NotImplementedError(
            "IbApiClient is not yet implemented. "
            "Use IbAsyncClient (ib_async) as the default backend."
        )

    def disconnect(self) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def is_connected(self) -> bool:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def place_order(self, contract: Any, order: Any) -> Any:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def cancel_order(self, order: Any) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def trades(self) -> list[Any]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def positions(self) -> list[Any]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def account_summary(self) -> list[Any]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def make_stock(self, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Any:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def make_order(self, **kwargs: Any) -> Any:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def qualify_contracts(self, *contracts: Any) -> list[Any]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def req_tickers(self, *contracts: Any) -> list[Any]:
        raise NotImplementedError("IbApiClient is not yet implemented.")
