from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.models import AccountRecord
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.books.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.services.books.rotation import resolve_book_rotation_schedule
from trading.services.books.rotation_metrics import build_rotation_strategy_metrics


@dataclass(frozen=True, slots=True)
class BookChallengerEvaluation:
    # The trading book being evaluated — the primary key of the flow.
    book_id: int
    incumbent_strategy: str
    incumbent: RotationStrategyMetrics
    challengers: list[RotationStrategyMetrics]
    # The book's evidence window (lookback is per-book since ADR 014).
    rolling_window_days: int
    window_start_day: str
    window_end_day: str


@dataclass(frozen=True, slots=True)
class ChallengerEvaluationRun:
    account_id: int
    account_name: str
    books: list[BookChallengerEvaluation]


def build_book_challenger_evaluations(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    as_of_iso: str,
    rolling_window_days: int | None = None,
) -> ChallengerEvaluationRun:
    """Evaluate champion vs challengers for the account's rotation-enabled books.

    Scheduling is book-owned (ADR 014): each book's resolved
    ``book_rotation_settings`` supply the enabled gate, the challenger
    schedule, and the evidence lookback. Books with rotation disabled are
    skipped. ``rolling_window_days`` overrides every book's lookback when
    given (the shadow-eval job's explicit window).
    """
    account_id = account.id
    books: list[BookChallengerEvaluation] = []
    for trading_book in enumerate_trading_books(conn, account_id=account_id):
        schedule_config = resolve_book_rotation_schedule(conn, book_id=trading_book.book.id)
        if not schedule_config.rotation_enabled:
            continue
        window_days = rolling_window_days if rolling_window_days is not None else schedule_config.lookback_days
        window_start_day, window_end_day = _resolve_window_bounds_shared(
            as_of_iso=as_of_iso,
            rolling_window_days=window_days,
        )
        incumbent_strategy = trading_book.assignment.strategy_name.strip()
        incumbent = build_rotation_strategy_metrics(
            conn,
            account=account,
            strategy_name=incumbent_strategy,
        )
        challengers: list[RotationStrategyMetrics] = []
        for strategy_name in schedule_config.schedule:
            if strategy_name == incumbent_strategy:
                continue
            challengers.append(
                build_rotation_strategy_metrics(
                    conn,
                    account=account,
                    strategy_name=strategy_name,
                )
            )
        books.append(
            BookChallengerEvaluation(
                book_id=trading_book.book.id,
                incumbent_strategy=incumbent_strategy,
                incumbent=incumbent,
                challengers=challengers,
                rolling_window_days=window_days,
                window_start_day=window_start_day,
                window_end_day=window_end_day,
            )
        )

    return ChallengerEvaluationRun(
        account_id=account_id,
        account_name=str(account.name),
        books=books,
    )
