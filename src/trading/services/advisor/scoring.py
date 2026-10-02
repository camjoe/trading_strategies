"""Score due advisor decisions against the alternative each one rejected.

Both arms are backtested over the window that actually followed the decision, through the
same engine, universe, sizing, and costs, so the verdict reflects the choice rather than the
market. The book's realized paper return and the benchmark's return are recorded alongside
as context; they never decide the verdict.
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from backtesting.models.backtest import BACKTEST_PURPOSE_STANDALONE, BacktestConfig, BacktestResult
from common.time import utc_now_iso
from trading.domain.advisor import counterfactual_verdict, due_for_scoring, outcome_window_end, plan_counterfactual
from trading.domain.metrics.returns import total_return_pct
from trading.models import AccountRecord
from trading.models.advisor import (
    OUTCOME_STATUS_INCONCLUSIVE,
    OUTCOME_STATUS_MEASURED,
    DecisionScoreResult,
    StrategyDecisionOutcome,
    StrategyDecisionRecord,
)
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.repositories.strategies import StrategyRepository
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import get_account

# Runs one metrics-only backtest; the interface binds the market-data provider into it.
RunBacktestFn = Callable[[sqlite3.Connection, BacktestConfig], BacktestResult]

# Months of indicator warm-up loaded before each arm's window, so both arms trade on warm
# signals from the decision date rather than spending the window warming up.
SCORING_WARMUP_MONTHS = 6
# Per-trade costs applied identically to both arms. Slippage matches the backtest CLI default.
SCORING_SLIPPAGE_BPS = 5.0
SCORING_FEE_PER_TRADE = 0.0
# The chosen arm's return when a decision disabled a strategy: the capital sits in cash.
CASH_ARM_RETURN_PCT = 0.0


def score_due_decisions(
    conn: sqlite3.Connection,
    *,
    run_backtest_fn: RunBacktestFn,
    account_name: str | None = None,
    as_of: date | None = None,
) -> list[DecisionScoreResult]:
    """Score every pending decision whose window closed by ``as_of`` (default: today, UTC).

    Each due decision ends ``measured`` with a verdict, or ``inconclusive`` with the reason it
    could not be scored. Either way it leaves the pending queue.
    """
    as_of_date = as_of or datetime.now(timezone.utc).date()
    account_id = get_account(conn, account_name).id if account_name is not None else None
    repository = StrategyDecisionRepository(conn)
    due = due_for_scoring(repository.fetch_pending(account_id=account_id), as_of=as_of_date)

    results: list[DecisionScoreResult] = []
    for record in due:
        account = AccountRepository(conn).fetch_by_id(account_id=record.account_id)
        if account is None:
            continue
        outcome = _score(conn, record, account=account, run_backtest_fn=run_backtest_fn)
        repository.update_outcome(strategy_decision_id=record.id, outcome=outcome)
        results.append(
            DecisionScoreResult(
                strategy_decision_id=record.id,
                account_name=account.name,
                decision_type=record.decision_type,
                outcome=outcome,
            )
        )
    return results


def _score(
    conn: sqlite3.Connection,
    record: StrategyDecisionRecord,
    *,
    account: AccountRecord,
    run_backtest_fn: RunBacktestFn,
) -> StrategyDecisionOutcome:
    window_start = datetime.fromisoformat(record.created_at).date()
    window_end = outcome_window_end(record)
    measured_at = utc_now_iso()

    def inconclusive(reason: str) -> StrategyDecisionOutcome:
        return StrategyDecisionOutcome(
            outcome_status=OUTCOME_STATUS_INCONCLUSIVE,
            outcome_window_start=window_start.isoformat(),
            outcome_window_end=window_end.isoformat(),
            outcome_note=reason,
            outcome_measured_at=measured_at,
        )

    plan = plan_counterfactual(record)
    if plan.unscorable_reason is not None or plan.alternative_strategy_id is None:
        return inconclusive(plan.unscorable_reason or "no rejected alternative")
    book = BookRepository(conn).fetch_by_id(book_id=record.book_id) if record.book_id is not None else None
    if book is None:
        return inconclusive("the decision's book no longer exists")
    tickers = book.trade_symbol_list()
    if not tickers:
        return inconclusive("the decision's book has no trade symbols")

    window = (window_start, window_end)
    try:
        with _universe_file(tickers) as tickers_file:
            alternative_key, alternative_result = _backtest_arm(
                conn, run_backtest_fn, account, plan.alternative_strategy_id, tickers_file, window
            )
            if plan.chosen_strategy_id is None:
                chosen_key, chosen_return = "cash", CASH_ARM_RETURN_PCT
            else:
                chosen_key, chosen_result = _backtest_arm(
                    conn, run_backtest_fn, account, plan.chosen_strategy_id, tickers_file, window
                )
                chosen_return = chosen_result.total_return_pct
    except (ValueError, LookupError) as error:
        return inconclusive(f"backtest failed: {error}")

    return StrategyDecisionOutcome(
        outcome_status=OUTCOME_STATUS_MEASURED,
        outcome_window_start=window_start.isoformat(),
        outcome_window_end=window_end.isoformat(),
        realized_return_pct=_paper_return(conn, book_id=book.id, window=window),
        realized_benchmark_return_pct=alternative_result.benchmark_return_pct,
        chosen_return_pct=chosen_return,
        alternative_return_pct=alternative_result.total_return_pct,
        outcome_verdict=counterfactual_verdict(
            chosen_return_pct=chosen_return,
            alternative_return_pct=alternative_result.total_return_pct,
        ),
        outcome_note=f"chosen {chosen_key} vs rejected {alternative_key}",
        outcome_measured_at=measured_at,
    )


def _strategy_key(conn: sqlite3.Connection, strategy_id: int) -> str:
    record = StrategyRepository(conn).fetch_by_id(strategy_id=strategy_id)
    if record is None:
        raise LookupError(f"strategy id {strategy_id} no longer exists")
    return record.strategy_key


def _backtest_arm(
    conn: sqlite3.Connection,
    run_backtest_fn: RunBacktestFn,
    account: AccountRecord,
    strategy_id: int,
    tickers_file: str,
    window: tuple[date, date],
) -> tuple[str, BacktestResult]:
    """Backtest one arm by its catalog key; the engine runs a variant with its own knobs."""
    strategy_key = _strategy_key(conn, strategy_id)
    start, end = window
    result = run_backtest_fn(
        conn,
        BacktestConfig(
            account_name=account.name,
            tickers_file=tickers_file,
            universe_history_dir=None,
            start=start.isoformat(),
            end=end.isoformat(),
            lookback_months=None,
            slippage_bps=SCORING_SLIPPAGE_BPS,
            fee_per_trade=SCORING_FEE_PER_TRADE,
            run_name=None,
            allow_approximate_leaps=False,
            strategy=strategy_key,
            purpose=BACKTEST_PURPOSE_STANDALONE,
            param_override=None,
            warmup_months=SCORING_WARMUP_MONTHS,
        ),
    )
    return strategy_key, result


def _paper_return(conn: sqlite3.Connection, *, book_id: int, window: tuple[date, date]) -> float | None:
    """The book's realized paper return across the window, or None without marks at both ends."""
    start, end = window
    snapshots = EquitySnapshotRepository(conn)
    first = snapshots.fetch_last_for_book_on_or_before_date(book_id=book_id, date_str=start.isoformat())
    last = snapshots.fetch_last_for_book_on_or_before_date(book_id=book_id, date_str=end.isoformat())
    if first is None or last is None or first.equity <= 0:
        return None
    return total_return_pct(first_equity=float(first.equity), last_equity=float(last.equity))


@contextmanager
def _universe_file(tickers: Sequence[str]) -> Iterator[str]:
    """A temporary ticker file holding the book's universe; the backtest reads its universe from a file."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="advisor_score_", delete=False, encoding="utf-8"
    )
    try:
        handle.write("\n".join(tickers) + "\n")
        handle.close()
        yield handle.name
    finally:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
