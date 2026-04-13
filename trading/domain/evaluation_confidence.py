from __future__ import annotations

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
) -> float:
    trade_confidence = compute_observation_confidence(
        trade_count,
        full_confidence_count=BACKTEST_TRADE_COUNT_FOR_FULL_CONFIDENCE,
    )
    snapshot_confidence = compute_observation_confidence(
        snapshot_count,
        full_confidence_count=BACKTEST_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE,
    )
    return clamp_confidence(
        (trade_confidence * BACKTEST_TRADE_CONFIDENCE_WEIGHT)
        + (snapshot_confidence * BACKTEST_SNAPSHOT_CONFIDENCE_WEIGHT)
    )


def compute_paper_live_confidence(*, snapshot_count: int | None) -> float:
    return compute_observation_confidence(
        snapshot_count,
        full_confidence_count=PAPER_LIVE_SNAPSHOT_COUNT_FOR_FULL_CONFIDENCE,
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
) -> float:
    weighted_values = [
        (backtest_confidence, BACKTEST_EVIDENCE_WEIGHT),
        (paper_live_confidence, PAPER_LIVE_EVIDENCE_WEIGHT),
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
) -> float | None:
    weighted_values: list[tuple[float, float]] = []
    if backtest_score is not None and backtest_confidence > 0:
        weighted_values.append(
            (
                backtest_score,
                backtest_confidence * BACKTEST_EVIDENCE_WEIGHT,
            )
        )
    if paper_live_score is not None and paper_live_confidence > 0:
        weighted_values.append(
            (
                paper_live_score,
                paper_live_confidence * PAPER_LIVE_EVIDENCE_WEIGHT,
            )
        )
    return _weighted_average(weighted_values)
