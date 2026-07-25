"""Native ``ibapi`` implementation placeholder for the IBKR socket client."""

from __future__ import annotations

from infrastructure.brokers.ibkr_socket.contracts import (
    IbkrAccountValue,
    IbkrOrderRequest,
    IbkrPosition,
    IbkrQuote,
    IbkrTrade,
)


class IbApiClient:
    """Native IBKR socket client; callback implementation is the next phase."""

    def connect(self, host: str, port: int, *, client_id: int) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def disconnect(self) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def is_connected(self) -> bool:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def place_order(self, order: IbkrOrderRequest) -> IbkrTrade:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def cancel_order(self, order_id: int) -> None:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def trades(self) -> list[IbkrTrade]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def positions(self) -> list[IbkrPosition]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def account_summary(self) -> list[IbkrAccountValue]:
        raise NotImplementedError("IbApiClient is not yet implemented.")

    def quotes(self, symbols: list[str]) -> list[IbkrQuote]:
        raise NotImplementedError("IbApiClient is not yet implemented.")
