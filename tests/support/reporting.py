from __future__ import annotations

from tests.support.books import ensure_default_book_id
from trading.models.evaluation import (
    BacktestFreshness,
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.snapshots import EquitySnapshotRepository


def insert_trade(
    conn,
    account_id: int,
    ticker: str,
    qty: float,
    price: float,
    trade_time: str = "2026-01-01T00:00:00Z",
) -> None:
    # Fills are the execution history (revision 0006); the replayed account
    # state sees this exactly like the retired trades row.
    from tests.support.fills import seed_fill_event

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker=ticker,
        side="buy",
        qty=qty,
        price=price,
        trade_time=trade_time,
    )


def insert_snapshot(conn, account_id: int, snapshot_time: str, equity: float) -> None:
    # Snapshots are book-keyed; the repository resolves the default book.
    EquitySnapshotRepository(conn).insert_for_book(
        book_id=ensure_default_book_id(conn, account_id),
        snapshot_time=snapshot_time,
        cash=equity,
        market_value=0.0,
        equity=equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )


def make_evaluation_artifact(
    *,
    account_id: int,
    account_name: str,
    backtest_return_pct: float | None = None,
    backtest_trade_count: int | None = None,
    paper_live_mode: str | None = None,
    paper_live_return_pct: float | None = None,
    paper_live_snapshot_count: int | None = None,
    blended_score: float | None = None,
    overall_confidence: float = 0.0,
    backtest_freshness: BacktestFreshness | None = None,
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(account_id=account_id, account_name=account_name),
        backtest=EvaluationBacktestEvidence(
            available=backtest_return_pct is not None,
            total_return_pct=backtest_return_pct,
            trade_count=backtest_trade_count,
        ),
        paper_live=EvaluationPaperLiveEvidence(
            available=paper_live_return_pct is not None,
            mode=paper_live_mode,
            return_pct=paper_live_return_pct,
            snapshot_count=paper_live_snapshot_count,
        ),
        confidence=EvaluationConfidence(
            overall_confidence=overall_confidence,
            blended_score=blended_score,
        ),
        diagnostics=EvaluationDiagnostics(backtest_freshness=backtest_freshness),
    )


__all__ = [
    "insert_snapshot",
    "insert_trade",
    "make_evaluation_artifact",
]
