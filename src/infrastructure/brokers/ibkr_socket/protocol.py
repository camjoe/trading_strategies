"""Backend-neutral client protocol for IBKR socket integrations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)


@runtime_checkable
class IbkrSocketClient(Protocol):
    """Interface implemented by each IBKR socket client backend."""

    def connect(self, host: str, port: int, *, client_id: int) -> None: ...

    def disconnect(self) -> None: ...

    def is_connected(self) -> bool: ...

    def place_order(self, order: IbkrOrderRequest) -> IbkrTrade: ...

    def cancel_order(self, order_id: int) -> None: ...

    def trades(self) -> list[IbkrTrade]: ...

    def positions(self) -> list[IbkrPosition]: ...

    def account_summary(self) -> list[IbkrAccountValue]: ...

    def quotes(self, symbols: list[str]) -> list[IbkrQuote]: ...
