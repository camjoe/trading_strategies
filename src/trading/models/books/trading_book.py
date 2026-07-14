from __future__ import annotations

from dataclasses import dataclass

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord


@dataclass(frozen=True, slots=True)
class TradingBook:
    """A book eligible to trade: active, non-default, with an open strategy assignment."""

    book: BookRecord
    assignment: BookAssignmentView
