"""Cash, positions, and average cost as one mutable object — no I/O."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Generic

from trading.domain.accounting.ledger import Number, buy_position_delta, sell_position_delta


@dataclass
class Holdings(Generic[Number]):
    """What an account or backtest holds part-way through a replay.

    Shared by the backtest (float) and the live replay (Decimal): the number type
    follows ``cash``. A ticker never traded reads as zero in ``positions`` and
    ``avg_cost``. ``buy`` and ``sell`` mutate in place; the fee is capitalized into
    the cost basis on a buy and charged against realized P&L on a sell.
    """

    cash: Number
    positions: dict[str, Number]
    avg_cost: dict[str, Number]
    realized_pnl: Number

    @classmethod
    def starting_with(cls, cash: Number) -> Holdings[Number]:
        zero = type(cash)()
        return cls(
            cash=cash,
            positions=defaultdict(type(cash)),
            avg_cost=defaultdict(type(cash)),
            realized_pnl=zero,
        )

    def buy(self, ticker: str, qty: Number, price: Number, fee: Number) -> None:
        """Raise the position, re-average its cost, and pay for the fill."""
        old_qty = self.positions[ticker]
        if old_qty + qty <= 0:
            raise ValueError(
                f"Buy of {qty} for {ticker} leaves a non-positive position ({old_qty + qty}); qty must be > 0."
            )
        delta = buy_position_delta(
            position_qty=old_qty, position_avg_cost=self.avg_cost[ticker], qty=qty, price=price, fee=fee
        )
        self.positions[ticker] = delta.ending_qty
        self.avg_cost[ticker] = delta.ending_avg_cost
        self.cash += delta.cash_delta

    def sell(self, ticker: str, qty: Number, price: Number, fee: Number) -> None:
        """Reduce the position, credit the proceeds, and book the realized P&L."""
        old_qty = self.positions[ticker]
        if qty > old_qty:
            raise ValueError(f"Invalid sell for {ticker}: trying to sell {qty}, holding {old_qty}.")
        delta = sell_position_delta(
            position_qty=old_qty, position_avg_cost=self.avg_cost[ticker], qty=qty, price=price, fee=fee
        )
        self.positions[ticker] = delta.ending_qty
        self.cash += delta.cash_delta
        self.realized_pnl += delta.realized_delta

    def open_positions(self) -> tuple[dict[str, Number], dict[str, Number]]:
        """The still-open ``(positions, avg_cost)``, without sold-out tickers.

        A closed position keeps its stale ``avg_cost`` after a sell: at zero quantity
        nothing reads it. Exact arithmetic over truncated quantities keeps a fully
        sold position at exactly zero, so ``qty > 0`` is a reliable open test.
        """
        open_qty = {ticker: qty for ticker, qty in self.positions.items() if qty > 0}
        open_cost = {ticker: self.avg_cost[ticker] for ticker in open_qty}
        return open_qty, open_cost
