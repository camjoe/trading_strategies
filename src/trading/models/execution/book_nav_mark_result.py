from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BookNavMarkResult:
    """Outcome of marking one book's positions to market.

    ``current_equity`` is the re-marked NAV (``current_cash`` + Σ marked position
    value). ``unpriced_symbols`` are positions with no valid live mark, held at
    cost basis (no unrealized P&L) — surfaced so callers can flag a stale book.
    """

    book_id: int
    current_cash: float
    current_equity: float
    unpriced_symbols: list[str] = field(default_factory=list)
