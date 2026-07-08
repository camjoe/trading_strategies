from __future__ import annotations

from dataclasses import dataclass

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord


@dataclass(frozen=True, slots=True)
class TradingBook:
    """A book eligible to trade: active, non-default, with an open strategy assignment.

    ``legacy_sleeve_id`` carries the book's legacy sleeve identity during the
    sleeve retirement window (audit rows + dual-write); ``None`` once books stand
    alone. Dies with SR-6.
    """

    book: BookRecord
    assignment: BookAssignmentView
    legacy_sleeve_id: int | None
