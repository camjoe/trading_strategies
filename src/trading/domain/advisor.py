"""Advisor policy: when a decision is due, which review flags to raise, and how a decision is scored.

Flags are prompts for a reviewer, not chosen actions; the digest never picks a decision. A decision
is scored against the alternative it rejected, not against the market.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from trading.domain.market.hours import add_us_equity_trading_days
from trading.models.advisor import (
    DECISION_TYPE_DISABLE_STRATEGY,
    DECISION_TYPE_RUN_EXPERIMENT,
    FLAG_BACKTEST_STALE,
    FLAG_DATA_GAPS,
    FLAG_DECISIONS_DUE,
    FLAG_NO_PAPER_EVIDENCE,
    FLAG_NO_WALK_FORWARD,
    FLAG_PAPER_RETURN_NEGATIVE,
    OUTCOME_VERDICT_HELPED,
    OUTCOME_VERDICT_HURT,
    OUTCOME_VERDICT_NEUTRAL,
    AdvisorFlag,
    CounterfactualPlan,
    StrategyDecisionRecord,
)
from trading.models.evaluation import (
    PAPER_LIVE_EVIDENCE_GAP,
    WALK_FORWARD_EVIDENCE_GAP,
    StrategyEvaluationArtifact,
)

# Arms whose returns differ by less than this many percentage points score neutral: one
# window cannot separate a gap that small from noise.
DECISION_NEUTRAL_BAND_PCT = 1.0

# Data gaps already reported by their own flag, so the data_gaps flag omits them.
_GAPS_WITH_THEIR_OWN_FLAG = frozenset({PAPER_LIVE_EVIDENCE_GAP, WALK_FORWARD_EVIDENCE_GAP})


def outcome_window_end(record: StrategyDecisionRecord) -> date:
    """The trading date a decision's outcome window closes: its UTC decision date plus the window."""
    decided_on = datetime.fromisoformat(record.created_at).date()
    return add_us_equity_trading_days(decided_on, record.outcome_window_days)


def due_for_scoring(records: Sequence[StrategyDecisionRecord], *, as_of: date) -> list[StrategyDecisionRecord]:
    """The pending records whose outcome window has closed on or before ``as_of``."""
    return [record for record in records if outcome_window_end(record) <= as_of]


def build_review_flags(
    evaluation: StrategyEvaluationArtifact,
    *,
    due_count: int,
) -> list[AdvisorFlag]:
    flags: list[AdvisorFlag] = []
    if due_count > 0:
        flags.append(AdvisorFlag(FLAG_DECISIONS_DUE, f"{due_count} decision(s) past their outcome window"))

    strategy = evaluation.basic.requested_strategy or "the active strategy"
    if not evaluation.walk_forward.available:
        flags.append(AdvisorFlag(FLAG_NO_WALK_FORWARD, f"no walk-forward evidence for {strategy}"))

    freshness = evaluation.diagnostics.backtest_freshness
    if freshness is not None and freshness.is_stale and freshness.age_days is not None:
        flags.append(
            AdvisorFlag(
                FLAG_BACKTEST_STALE,
                f"backtest evidence is {freshness.age_days:.0f} days old "
                f"(stale after {freshness.stale_threshold_days})",
            )
        )

    paper = evaluation.paper_live
    if not paper.available:
        flags.append(AdvisorFlag(FLAG_NO_PAPER_EVIDENCE, "no paper-trading evidence yet"))
    elif paper.return_pct is not None and paper.return_pct < 0:
        flags.append(
            AdvisorFlag(
                FLAG_PAPER_RETURN_NEGATIVE,
                f"paper return is {paper.return_pct:.2f}% (absolute, not benchmark-relative)",
            )
        )

    other_gaps = [gap for gap in evaluation.diagnostics.data_gaps if gap not in _GAPS_WITH_THEIR_OWN_FLAG]
    if other_gaps:
        flags.append(AdvisorFlag(FLAG_DATA_GAPS, ", ".join(other_gaps)))
    return flags


def plan_counterfactual(record: StrategyDecisionRecord) -> CounterfactualPlan:
    """The arms a decision is scored on: what it put or kept in place versus what it rejected.

    A disabled strategy's chosen arm is cash; ``run_experiment`` gathers evidence rather than
    choosing between strategies, so it has no counterfactual.
    """
    if record.decision_type == DECISION_TYPE_RUN_EXPERIMENT:
        return CounterfactualPlan(unscorable_reason="run_experiment chooses no strategy to compare")
    if record.strategy_id is None:
        return CounterfactualPlan(unscorable_reason="no strategy recorded on the decision")
    if record.decision_type == DECISION_TYPE_DISABLE_STRATEGY:
        return CounterfactualPlan(chosen_strategy_id=None, alternative_strategy_id=record.strategy_id)
    if record.alternative_strategy_id is None:
        return CounterfactualPlan(unscorable_reason="no rejected alternative recorded on the decision")
    return CounterfactualPlan(
        chosen_strategy_id=record.strategy_id,
        alternative_strategy_id=record.alternative_strategy_id,
    )


def counterfactual_verdict(*, chosen_return_pct: float, alternative_return_pct: float) -> str:
    """helped / hurt when the chosen arm beat / trailed the rejected one by more than the band."""
    edge = chosen_return_pct - alternative_return_pct
    if edge > DECISION_NEUTRAL_BAND_PCT:
        return OUTCOME_VERDICT_HELPED
    if edge < -DECISION_NEUTRAL_BAND_PCT:
        return OUTCOME_VERDICT_HURT
    return OUTCOME_VERDICT_NEUTRAL
