from __future__ import annotations

from trading.domain.evaluation_decision_score import derive_decision_score
from trading.models.evaluation import StrategyEvaluationArtifact


def _backtest_stale(artifact: StrategyEvaluationArtifact) -> bool:
    freshness = artifact.diagnostics.backtest_freshness
    return bool(freshness is not None and freshness.is_stale)


def build_evaluation_summary_payload(artifact: StrategyEvaluationArtifact) -> dict[str, object]:
    decision = derive_decision_score(artifact)
    return {
        "blendedScore": decision.score,
        "overallConfidence": decision.confidence,
        "backtestConfidence": decision.backtest_confidence,
        "paperLiveConfidence": decision.paper_live_confidence,
        "dataGaps": list(decision.data_gaps),
        "backtestStale": _backtest_stale(artifact),
    }


def _backtest_freshness_payload(artifact: StrategyEvaluationArtifact) -> dict[str, object]:
    freshness = artifact.diagnostics.backtest_freshness
    if freshness is None:
        return {"available": False, "ageDays": None, "isStale": False, "staleThresholdDays": None}
    return {
        "available": freshness.available,
        "ageDays": freshness.age_days,
        "isStale": freshness.is_stale,
        "staleThresholdDays": freshness.stale_threshold_days,
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
        "backtestFreshness": _backtest_freshness_payload(artifact),
    }


__all__ = [
    "build_evaluation_detail_payload",
    "build_evaluation_summary_payload",
]
