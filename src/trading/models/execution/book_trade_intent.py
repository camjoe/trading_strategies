from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookTradeIntent:
    """A single approved-to-submit trade for one book (the clean-schema execution unit).

    A book is the execution unit for both a plain account's default book and any
    additional books, so this one contract replaces the per-mode selection tuples
    that fed the two legacy submission paths. Passive data only — the execution service maps it to a
    ``BrokerOrder`` and persists the outcome to the clean book-keyed tables.
    """

    book_id: int
    account_id: int
    strategy_id: int | None
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    requested_price: float | None
    order_type: str = "market"
    time_in_force: str = "day"
