"""Advisor digest policy: when a decision is due for scoring, and which review flags to raise.

Flags are prompts for a reviewer, not chosen actions; the digest never picks a decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from trading.domain.market.hours import add_us_equity_trading_days
from trading.models.advisor import (
    FLAG_BACKTEST_STALE,
    FLAG_DATA_GAPS,
    FLAG_DECISIONS_DUE,
    FLAG_NO_PAPER_EVIDENCE,
    FLAG_NO_WALK_FORWARD,
    FLAG_PAPER_RETURN_NEGATIVE,
    AdvisorFlag,
    StrategyDecisionRecord,
)
from trading.models.evaluation import (
    PAPER_LIVE_EVIDENCE_GAP,
    WALK_FORWARD_EVIDENCE_GAP,
    StrategyEvaluationArtifact,
)

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
