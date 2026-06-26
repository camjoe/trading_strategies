from __future__ import annotations

from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationPaperLiveEvidence,
    StrategyEvaluationArtifact,
)


def insert_trade(
    conn,
    account_id: int,
    ticker: str,
    qty: float,
    price: float,
    trade_time: str = "2026-01-01T00:00:00Z",
) -> None:
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, ticker, "buy", qty, price, 0.0, trade_time, "entry"),
    )


def insert_snapshot(conn, account_id: int, snapshot_time: str, equity: float) -> None:
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, snapshot_time, equity, 0.0, equity, 0.0, 0.0),
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
    )


__all__ = [
    "insert_snapshot",
    "insert_trade",
    "make_evaluation_artifact",
]
