from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from trading.domain.rotation import parse_rotation_schedule
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.models import AccountRecord
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.books.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.services.books.rotation_metrics import build_rotation_strategy_metrics

DEFAULT_CHALLENGER_ROLLING_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class BookChallengerEvaluation:
    # The trading book being evaluated — the primary key of the flow.
    book_id: int
    incumbent_strategy: str
    incumbent: RotationStrategyMetrics
    challengers: list[RotationStrategyMetrics]


@dataclass(frozen=True, slots=True)
class ChallengerEvaluationRun:
    account_id: int
    account_name: str
    window_start_day: str
    window_end_day: str
    books: list[BookChallengerEvaluation]


def _resolve_strategy_schedule(account: AccountRecord) -> list[str]:
    try:
        schedule = parse_rotation_schedule(account.rotation_schedule)
    except ValueError:
        schedule = []
    if not schedule:
        base_strategy = str(account.strategy).strip()
        return [base_strategy] if base_strategy else []
    return [name for name in schedule if name]


def _resolve_window_bounds(*, as_of_iso: str, rolling_window_days: int) -> tuple[str, str]:
    return _resolve_window_bounds_shared(as_of_iso=as_of_iso, rolling_window_days=rolling_window_days)


def build_book_challenger_evaluations(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    as_of_iso: str,
    rolling_window_days: int = DEFAULT_CHALLENGER_ROLLING_WINDOW_DAYS,
) -> ChallengerEvaluationRun:
    account_id = account.id
    schedule = _resolve_strategy_schedule(account)
    window_start_day, window_end_day = _resolve_window_bounds(
        as_of_iso=as_of_iso,
        rolling_window_days=rolling_window_days,
    )
    param_set_repo = StrategyParamSetRepository(conn)
    # Book-native enumeration: active, non-default, openly assigned books.
    books: list[BookChallengerEvaluation] = []
    for trading_book in enumerate_trading_books(conn, account_id=account_id):
        incumbent_strategy = trading_book.assignment.strategy_name.strip()
        incumbent = build_rotation_strategy_metrics(
            conn,
            account=account,
            strategy_name=incumbent_strategy,
            param_set_id=trading_book.assignment.param_set_id,
        )
        challengers: list[RotationStrategyMetrics] = []
        for strategy_name in schedule:
            if strategy_name == incumbent_strategy:
                continue
            active_param_set = param_set_repo.fetch_active(strategy_name=strategy_name)
            challengers.append(
                build_rotation_strategy_metrics(
                    conn,
                    account=account,
                    strategy_name=strategy_name,
                    param_set_id=active_param_set.id if active_param_set is not None else None,
                )
            )
        books.append(
            BookChallengerEvaluation(
                book_id=trading_book.book.id,
                incumbent_strategy=incumbent_strategy,
                incumbent=incumbent,
                challengers=challengers,
            )
        )

    return ChallengerEvaluationRun(
        account_id=account_id,
        account_name=str(account.name),
        window_start_day=window_start_day,
        window_end_day=window_end_day,
        books=books,
    )
