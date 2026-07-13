from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookAssignmentView:
    """A book's open strategy assignment, resolved for trading-path consumers.

    Carries the catalog-resolved strategy label alongside the raw ids so callers
    (intent generation, rotation, candidate enumeration) do not re-resolve it.
    """

    book_id: int
    strategy_id: int
    strategy_name: str
