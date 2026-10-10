from __future__ import annotations

from dataclasses import dataclass

# Confidence scores are normalized onto a 0.0–1.0 scale.
MIN_CONFIDENCE = 0.0

# Confidence scores saturate at 1.0 even when evidence volume keeps growing.
MAX_CONFIDENCE = 1.0

# Backtests are treated as well-covered once they accumulate this many trades.
BACKTEST_TRADE_COUNT_FOR_FULL_CONFIDENCE = 50

# Backtests are treated as well-covered once they accumulate this many snapshots.
BACKTEST_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE = 60

# Persisted paper/live evidence is treated as well-covered after this many snapshots.
PAPER_LIVE_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE = 30

# Trade count is the stronger backtest confidence signal because it measures decision volume.
BACKTEST_TRADE_CONFIDENCE_WEIGHT = 0.7

# Snapshot count is a secondary backtest confidence signal for equity-curve depth.
BACKTEST_SNAPSHOT_CONFIDENCE_WEIGHT = 0.3

# Canonical evaluation blends toward backtests slightly because paper/live history is often sparse.
BACKTEST_EVIDENCE_WEIGHT = 0.6

# Paper/live evidence still contributes, but conservatively, in the initial blend.
PAPER_LIVE_EVIDENCE_WEIGHT = 0.4


@dataclass(frozen=True)
class EvaluationConfidenceSettings:
    backtest_trade_count_for_full_confidence: int = BACKTEST_TRADE_COUNT_FOR_FULL_CONFIDENCE
    backtest_snapshot_count_for_full_confidence: int = BACKTEST_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE
    paper_live_snapshot_count_for_full_confidence: int = PAPER_LIVE_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE
    backtest_trade_confidence_weight: float = BACKTEST_TRADE_CONFIDENCE_WEIGHT
    backtest_snapshot_confidence_weight: float = BACKTEST_SNAPSHOT_CONFIDENCE_WEIGHT
    backtest_evidence_weight: float = BACKTEST_EVIDENCE_WEIGHT
    paper_live_evidence_weight: float = PAPER_LIVE_EVIDENCE_WEIGHT


def clamp_confidence(value: float) -> float:
    return max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, value))


def compute_observation_confidence(
    observation_count: int | None,
    *,
    full_confidence_count: int,
) -> float:
    if observation_count is None or observation_count <= 0:
        return MIN_CONFIDENCE
    return clamp_confidence(observation_count / full_confidence_count)


def compute_backtest_confidence(
    *,
    trade_count: int | None,
    snapshot_count: int | None,
    settings: EvaluationConfidenceSettings | None = None,
) -> float:
    resolved = settings or EvaluationConfidenceSettings()
    trade_confidence = compute_observation_confidence(
        trade_count,
        full_confidence_count=resolved.backtest_trade_count_for_full_confidence,
    )
    snapshot_confidence = compute_observation_confidence(
        snapshot_count,
        full_confidence_count=resolved.backtest_snapshot_count_for_full_confidence,
    )
    return clamp_confidence(
        (trade_confidence * resolved.backtest_trade_confidence_weight)
        + (snapshot_confidence * resolved.backtest_snapshot_confidence_weight)
    )


def compute_paper_live_confidence(
    *,
    snapshot_count: int | None,
    settings: EvaluationConfidenceSettings | None = None,
) -> float:
    resolved = settings or EvaluationConfidenceSettings()
    return compute_observation_confidence(
        snapshot_count,
        full_confidence_count=resolved.paper_live_snapshot_count_for_full_confidence,
    )


def _weighted_average(weighted_values: list[tuple[float, float]]) -> float | None:
    total_weight = sum(weight for _value, weight in weighted_values)
    if total_weight <= 0:
        return None
    numerator = sum(value * weight for value, weight in weighted_values)
    return numerator / total_weight


def compute_overall_confidence(
    *,
    backtest_confidence: float,
    paper_live_confidence: float,
    settings: EvaluationConfidenceSettings | None = None,
) -> float:
    resolved = settings or EvaluationConfidenceSettings()
    weighted_values = [
        (backtest_confidence, resolved.backtest_evidence_weight),
        (paper_live_confidence, resolved.paper_live_evidence_weight),
    ]
    average = _weighted_average(weighted_values)
    if average is None:
        return MIN_CONFIDENCE
    return clamp_confidence(average)


def compute_blended_score(
    *,
    backtest_score: float | None,
    paper_live_score: float | None,
    backtest_confidence: float,
    paper_live_confidence: float,
    settings: EvaluationConfidenceSettings | None = None,
) -> float | None:
    resolved = settings or EvaluationConfidenceSettings()
    weighted_values: list[tuple[float, float]] = []
    if backtest_score is not None and backtest_confidence > 0:
        weighted_values.append(
            (
                backtest_score,
                backtest_confidence * resolved.backtest_evidence_weight,
            )
        )
    if paper_live_score is not None and paper_live_confidence > 0:
        weighted_values.append(
            (
                paper_live_score,
                paper_live_confidence * resolved.paper_live_evidence_weight,
            )
        )
    return _weighted_average(weighted_values)
