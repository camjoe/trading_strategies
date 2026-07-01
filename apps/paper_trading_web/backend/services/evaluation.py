from __future__ import annotations

from trading.models.evaluation import StrategyEvaluationArtifact


def build_evaluation_summary_payload(artifact: StrategyEvaluationArtifact) -> dict[str, object]:
    confidence = artifact.confidence
    return {
        "blendedScore": confidence.blended_score,
        "overallConfidence": confidence.overall_confidence,
        "backtestConfidence": confidence.backtest_confidence,
        "paperLiveConfidence": confidence.paper_live_confidence,
        "dataGaps": list(artifact.diagnostics.data_gaps),
    }


def build_evaluation_detail_payload(artifact: StrategyEvaluationArtifact) -> dict[str, object]:
    backtest = artifact.backtest
    walk_forward = artifact.walk_forward
    paper_live = artifact.paper_live
    return {
        "backtest": {
            "available": backtest.available,
            "returnPct": backtest.total_return_pct,
            "tradeCount": backtest.trade_count,
            "snapshotCount": backtest.snapshot_count,
            "maxDrawdownPct": backtest.max_drawdown_pct,
        },
        "walkForward": {
            "available": walk_forward.available,
            "grouped": walk_forward.grouped,
            "averageReturnPct": walk_forward.average_return_pct,
            "bestReturnPct": walk_forward.best_return_pct,
            "worstReturnPct": walk_forward.worst_return_pct,
        },
        "paperLive": {
            "available": paper_live.available,
            "returnPct": paper_live.return_pct,
            "snapshotCount": paper_live.snapshot_count,
            "sourceLevel": paper_live.source_level,
            "strategyIsolated": paper_live.strategy_isolated,
        },
        "confidence": build_evaluation_summary_payload(artifact),
        "dataGaps": list(artifact.diagnostics.data_gaps),
    }


__all__ = [
    "build_evaluation_detail_payload",
    "build_evaluation_summary_payload",
]
