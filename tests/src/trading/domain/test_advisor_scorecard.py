from __future__ import annotations

import pytest

from trading.domain.advisor_scorecard import (
    MIN_DECISIONS_FOR_RANKING,
    build_scorecard_groups,
    edge_pct,
    find_leader,
    mean_edge_interval,
    regime_of,
)
from trading.models.advisor import StrategyDecisionOutcome, StrategyDecisionRecord

_next_id = iter(range(1, 10_000))


def _measured(
    *,
    agent: str = "agent:a/v1",
    verdict: str = "helped",
    chosen: float = 2.0,
    alternative: float = 0.0,
    benchmark: float | None = 0.0,
    decision_type: str = "hold",
) -> StrategyDecisionRecord:
    return StrategyDecisionRecord(
        id=next(_next_id),
        account_id=1,
        decision_type=decision_type,
        rationale="r",
        evidence_json="{}",
        decided_by=agent,
        created_at="2026-08-03T00:00:00Z",
        outcome=StrategyDecisionOutcome(
            outcome_status="measured",
            outcome_verdict=verdict,
            chosen_return_pct=chosen,
            alternative_return_pct=alternative,
            realized_benchmark_return_pct=benchmark,
            outcome_measured_at="2026-09-01T00:00:00Z",
        ),
    )


def _inconclusive(*, agent: str = "agent:a/v1") -> StrategyDecisionRecord:
    return StrategyDecisionRecord(
        id=next(_next_id),
        account_id=1,
        decision_type="run_experiment",
        rationale="r",
        evidence_json="{}",
        decided_by=agent,
        created_at="2026-08-03T00:00:00Z",
        outcome=StrategyDecisionOutcome(outcome_status="inconclusive", outcome_note="nothing to compare"),
    )


@pytest.mark.parametrize(
    ("benchmark", "regime"),
    [(None, "unknown"), (3.2, "up"), (-2.4, "down"), (1.0, "flat"), (-1.0, "flat"), (0.0, "flat")],
)
def test_regime_follows_the_benchmark_with_a_one_point_band(benchmark: float | None, regime: str) -> None:
    assert regime_of(benchmark) == regime


def test_edge_is_chosen_minus_rejected_and_needs_both_arms() -> None:
    assert edge_pct(_measured(chosen=3.0, alternative=1.0)) == 2.0
    assert edge_pct(_inconclusive()) is None


def test_interval_needs_two_edges_and_is_reproducible() -> None:
    assert mean_edge_interval([1.0]) is None
    edges = [0.5, -0.2, 1.4, 0.9, 0.1]
    first = mean_edge_interval(edges)
    assert first == mean_edge_interval(edges)
    assert first is not None
    low, high = first
    assert low <= sum(edges) / len(edges) <= high


def test_constant_edges_give_a_zero_width_interval() -> None:
    assert mean_edge_interval([1.0, 1.0, 1.0]) == pytest.approx((1.0, 1.0))


def test_group_counts_points_scorable_rate_and_regime_points() -> None:
    records = [
        _measured(verdict="helped", benchmark=3.0),
        _measured(verdict="hurt", benchmark=3.0),
        _measured(verdict="helped", benchmark=-2.0),
        _inconclusive(),
    ]

    (group,) = build_scorecard_groups(records, group_by="agent")

    assert (group.scored_count, group.measured_count) == (4, 3)
    assert group.scorable_rate == pytest.approx(0.75)
    assert group.points == 1
    assert group.points_by_regime == {"up": 0, "flat": 0, "down": 1}
    assert group.rankable is False


def test_a_group_becomes_rankable_at_the_minimum_measured_count() -> None:
    records = [_measured() for _ in range(MIN_DECISIONS_FOR_RANKING)]
    (group,) = build_scorecard_groups(records, group_by="agent")
    assert group.rankable is True


def test_groups_by_decision_type_and_regime() -> None:
    records = [
        _measured(decision_type="hold", benchmark=3.0),
        _measured(decision_type="adjust_params", benchmark=-3.0),
    ]
    assert {group.key for group in build_scorecard_groups(records, group_by="decision_type")} == {
        "hold",
        "adjust_params",
    }
    assert {group.key for group in build_scorecard_groups(records, group_by="regime")} == {"up", "down"}


def test_unknown_grouping_raises() -> None:
    with pytest.raises(ValueError, match="Unknown scorecard grouping"):
        build_scorecard_groups([_measured()], group_by="mood")


def _rankable_group(agent: str, edges: list[float]):
    records = [_measured(agent=agent, chosen=edge, alternative=0.0) for edge in edges]
    (group,) = build_scorecard_groups(records, group_by="agent")
    return group


def test_leader_needs_an_interval_wholly_above_the_rest() -> None:
    strong = _rankable_group("agent:strong/v1", [3.0 + 0.1 * (i % 3) for i in range(MIN_DECISIONS_FOR_RANKING)])
    weak = _rankable_group("agent:weak/v1", [0.1 * (i % 3) for i in range(MIN_DECISIONS_FOR_RANKING)])
    assert find_leader([weak, strong]) == "agent:strong/v1"


def test_overlapping_intervals_have_no_leader() -> None:
    noisy = [(-1.0) ** i * 2.0 for i in range(MIN_DECISIONS_FOR_RANKING)]
    first = _rankable_group("agent:first/v1", noisy)
    second = _rankable_group("agent:second/v1", [edge + 0.1 for edge in noisy])
    assert find_leader([first, second]) is None


def test_a_single_rankable_group_has_no_leader() -> None:
    only = _rankable_group("agent:only/v1", [1.0] * MIN_DECISIONS_FOR_RANKING)
    assert find_leader([only]) is None
