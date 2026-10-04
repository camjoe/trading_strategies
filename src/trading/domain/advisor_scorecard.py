"""Advisor scorecard statistics: points, edge with a bootstrap interval, and regime breakdown.

A verdict is worth +1 / 0 / -1, but comparisons use the edge (chosen-arm return minus
rejected-arm return) with an interval, never a bare points total. Each measured window is
tagged with the market regime it fell in, so a defensive decision judged in a rising market
reads as what it is.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np

from trading.models.advisor import (
    OUTCOME_STATUS_MEASURED,
    OUTCOME_VERDICT_HELPED,
    OUTCOME_VERDICT_HURT,
    OUTCOME_VERDICT_NEUTRAL,
    REGIME_DOWN,
    REGIME_FLAT,
    REGIME_UNKNOWN,
    REGIME_UP,
    REGIMES,
    SCORECARD_GROUP_AGENT,
    SCORECARD_GROUP_DECISION_TYPE,
    SCORECARD_GROUP_REGIME,
    ScorecardGroup,
    StrategyDecisionRecord,
)

VERDICT_POINTS = {OUTCOME_VERDICT_HELPED: 1, OUTCOME_VERDICT_NEUTRAL: 0, OUTCOME_VERDICT_HURT: -1}

# A window whose benchmark moved more than this many percentage points either way is up or down;
# it matches the verdict's neutral band.
REGIME_THRESHOLD_PCT = 1.0
# Measured decisions a group needs before it is ranked against others.
MIN_DECISIONS_FOR_RANKING = 20
# Two-sided coverage of the mean-edge interval.
EDGE_INTERVAL_CONFIDENCE = 0.90
# Bootstrap resamples, and a fixed seed so the same ledger always prints the same interval.
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261003
# Fewest edges an interval can be resampled from.
_MIN_EDGES_FOR_INTERVAL = 2


def regime_of(benchmark_return_pct: float | None) -> str:
    if benchmark_return_pct is None:
        return REGIME_UNKNOWN
    if benchmark_return_pct > REGIME_THRESHOLD_PCT:
        return REGIME_UP
    if benchmark_return_pct < -REGIME_THRESHOLD_PCT:
        return REGIME_DOWN
    return REGIME_FLAT


def edge_pct(record: StrategyDecisionRecord) -> float | None:
    """Chosen-arm minus rejected-arm return for a measured decision, else None."""
    outcome = record.outcome
    if outcome.chosen_return_pct is None or outcome.alternative_return_pct is None:
        return None
    return outcome.chosen_return_pct - outcome.alternative_return_pct


def mean_edge_interval(edges: Sequence[float]) -> tuple[float, float] | None:
    """A bootstrap percentile interval for the mean edge, or None with too few edges."""
    if len(edges) < _MIN_EDGES_FOR_INTERVAL:
        return None
    values = np.asarray(edges, dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = rng.choice(values, size=(BOOTSTRAP_RESAMPLES, len(values)), replace=True).mean(axis=1)
    tail = (1.0 - EDGE_INTERVAL_CONFIDENCE) / 2.0 * 100.0
    low, high = np.percentile(means, [tail, 100.0 - tail])
    return float(low), float(high)


def _group_key(group_by: str) -> Callable[[StrategyDecisionRecord], str]:
    if group_by == SCORECARD_GROUP_AGENT:
        return lambda record: record.decided_by
    if group_by == SCORECARD_GROUP_DECISION_TYPE:
        return lambda record: record.decision_type
    if group_by == SCORECARD_GROUP_REGIME:
        return lambda record: regime_of(record.outcome.realized_benchmark_return_pct)
    raise ValueError(f"Unknown scorecard grouping '{group_by}'.")


def _summarize(key: str, records: Sequence[StrategyDecisionRecord]) -> ScorecardGroup:
    measured = [record for record in records if record.outcome.outcome_status == OUTCOME_STATUS_MEASURED]
    edges = [edge for edge in (edge_pct(record) for record in measured) if edge is not None]
    points_by_regime = {regime: 0 for regime in REGIMES}
    for record in measured:
        regime = regime_of(record.outcome.realized_benchmark_return_pct)
        if regime in points_by_regime:
            points_by_regime[regime] += VERDICT_POINTS.get(record.outcome.outcome_verdict or "", 0)
    return ScorecardGroup(
        key=key,
        scored_count=len(records),
        measured_count=len(measured),
        scorable_rate=len(measured) / len(records) if records else 0.0,
        points=sum(VERDICT_POINTS.get(record.outcome.outcome_verdict or "", 0) for record in measured),
        mean_edge_pct=float(np.mean(edges)) if edges else None,
        edge_interval=mean_edge_interval(edges),
        points_by_regime=points_by_regime,
        rankable=len(measured) >= MIN_DECISIONS_FOR_RANKING,
    )


def build_scorecard_groups(records: Sequence[StrategyDecisionRecord], *, group_by: str) -> list[ScorecardGroup]:
    """One group per key, rankable groups first by mean edge, then the rest by measured count."""
    key_of = _group_key(group_by)
    grouped: dict[str, list[StrategyDecisionRecord]] = defaultdict(list)
    for record in records:
        grouped[key_of(record)].append(record)
    groups = [_summarize(key, members) for key, members in grouped.items()]
    return sorted(
        groups,
        key=lambda group: (
            not group.rankable,
            -(group.mean_edge_pct if group.mean_edge_pct is not None and group.rankable else 0.0),
            -group.measured_count,
            group.key,
        ),
    )


def find_leader(groups: Sequence[ScorecardGroup]) -> str | None:
    """The rankable group whose interval lies wholly above every other rankable group's, if any."""
    rankable = [group for group in groups if group.rankable and group.edge_interval is not None]
    if len(rankable) < 2:
        return None
    for candidate in rankable:
        interval = candidate.edge_interval
        if interval is None:
            continue
        others = [group for group in rankable if group is not candidate]
        if all(other.edge_interval is not None and interval[0] > other.edge_interval[1] for other in others):
            return candidate.key
    return None
