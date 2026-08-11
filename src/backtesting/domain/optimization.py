"""Walk-forward optimization: candidate search, objective scoring, OOS aggregation.

Three stages of one run. The search expands a bounded grid into candidates, the
objective scores each training result and picks a window's winner, and the
aggregation compounds the resulting out-of-sample windows into one series long
after the run finished.

Pure domain math: the service layer supplies training results and OOS equity marks.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date, timedelta
from itertools import product
from typing import Any

from backtesting.domain.metrics import calmar_ratio
from backtesting.models.optimizer import (
    CandidateResult,
    CompoundedOOSPoint,
    CompoundedOOSSeries,
    OOSReturnSegment,
)
from common.constants import PERCENT_SCALE
from common.json_columns import dumps_json_column
from trading.domain.evaluation.risk_limits import MAX_ACCEPTABLE_DRAWDOWN_PCT
from trading.domain.exceptions import ValidationError

# What makes the objective calmar_v1 rather than a plain Calmar ratio: a
# one-percentage-point drawdown floor, so a (near-)zero-drawdown candidate stays
# finite and rankable instead of dividing by ~0.
CALMAR_V1_DRAWDOWN_FLOOR_PCT = 1.0

# Deliberately lower than the promotion gate's MIN_RESEARCH_BACKTEST_TRADE_COUNT: this
# counts trades in a single training window, while promotion counts them across a full
# backtest.
MIN_CANDIDATE_TRADES = 3
MAX_DRAWDOWN_ELIGIBILITY_PCT = MAX_ACCEPTABLE_DRAWDOWN_PCT


def params_fingerprint(params: dict[str, Any]) -> str:
    """Content hash of a candidate's parameters.

    Hashes the same canonical JSON a trial row stores, so two equal parameter sets
    collide by design — the basis for the one-candidate-per-window uniqueness
    constraint on trials.
    """
    return hashlib.sha256(dumps_json_column(params).encode("utf-8")).hexdigest()


def generate_candidates(search_space: dict[str, list[Any]], *, budget: int) -> list[dict[str, Any]]:
    """Expand a bounded search space into an ordered candidate list.

    Names are sorted before the Cartesian product, so candidate indices are stable
    across runs. A product larger than ``budget`` is rejected rather than truncated,
    so a run always evaluates every candidate it generated.
    """
    if not search_space:
        raise ValidationError("search_space must define at least one parameter.")

    names = sorted(search_space)
    value_lists: list[list[Any]] = []
    total = 1
    for name in names:
        values = list(search_space[name])
        if not values:
            raise ValidationError(f"search_space['{name}'] must have at least one value.")
        value_lists.append(values)
        total *= len(values)

    if total > budget:
        raise ValidationError(
            f"Grid Cartesian product ({total}) exceeds candidate budget ({budget}). "
            "Narrow the search space or raise the budget."
        )

    return [dict(zip(names, combo)) for combo in product(*value_lists)]


def evaluate_candidate(
    *,
    index: int,
    params: dict[str, Any],
    annualized_return_pct: float | None,
    max_drawdown_pct: float,
    trade_count: int,
) -> CandidateResult:
    """Score one training-interval result and record whether it is eligible at all."""
    rejection = _rejection_reason(annualized_return_pct, max_drawdown_pct, trade_count)
    score = (
        None
        if rejection is not None
        else calmar_ratio(
            annualized_return_pct=annualized_return_pct,
            max_drawdown_pct_value=max_drawdown_pct,
            drawdown_floor_pct=CALMAR_V1_DRAWDOWN_FLOOR_PCT,
        )
    )
    return CandidateResult(
        index=index,
        params=params,
        annualized_return_pct=annualized_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        trade_count=trade_count,
        score=score,
        eligible=rejection is None,
        rejection_reason=rejection,
    )


def _rejection_reason(
    annualized_return_pct: float | None,
    max_drawdown_pct: float,
    trade_count: int,
) -> str | None:
    # There is deliberately no positive-return gate: a candidate that lost money in a
    # down regime stays selectable (best-of-field), and its OOS/holdout run is the judge.
    if trade_count < MIN_CANDIDATE_TRADES:
        return f"too_few_trades ({trade_count} < {MIN_CANDIDATE_TRADES})"
    if annualized_return_pct is None:
        return "no_annualized_return"
    if max_drawdown_pct < MAX_DRAWDOWN_ELIGIBILITY_PCT:
        return f"drawdown_exceeds_limit ({max_drawdown_pct:.2f}% < {MAX_DRAWDOWN_ELIGIBILITY_PCT:.2f}%)"
    return None


def select_winner(results: list[CandidateResult]) -> CandidateResult:
    """Pick the best eligible candidate, raising when none are.

    "Least-bad" is not a valid selection, so a window with no eligible candidate fails
    rather than promoting a rejected one.
    """
    eligible = [result for result in results if result.eligible]
    if not eligible:
        tally = Counter((result.rejection_reason or "unknown").split(" (")[0] for result in results)
        breakdown = ", ".join(f"{reason} x{count}" for reason, count in sorted(tally.items()))
        raise ValidationError(
            f"No eligible candidate among {len(results)} evaluated ({breakdown}); "
            "refusing to select a rejected candidate."
        )
    return min(eligible, key=_rank_key)


def _rank_key(result: CandidateResult) -> tuple[float, float, float, int, int]:
    # Lowest tuple wins, so every "higher is better" field is sign-flipped. Ties break
    # on the candidate index, which makes the ordering deterministic across runs.
    return (
        -(result.score or 0.0),
        -(result.annualized_return_pct or 0.0),
        abs(result.max_drawdown_pct),
        -result.trade_count,
        result.index,
    )


def compound_oos_returns(segments: list[OOSReturnSegment]) -> CompoundedOOSSeries:
    """Compound per-window OOS returns into a single chronological series.

    Segments must already be in chronological order and must not overlap. A segment
    whose interval does not abut the previous one is flagged ``gap_before``.
    """
    points: list[CompoundedOOSPoint] = []
    growth = 1.0
    previous_end: date | None = None
    for segment in segments:
        growth *= 1.0 + segment.return_pct / PERCENT_SCALE
        gap_before = previous_end is not None and segment.test_start > previous_end + timedelta(days=1)
        points.append(
            CompoundedOOSPoint(
                window_index=segment.window_index,
                test_start=segment.test_start,
                test_end=segment.test_end,
                period_return_pct=segment.return_pct,
                cumulative_return_pct=(growth - 1.0) * PERCENT_SCALE,
                gap_before=gap_before,
            )
        )
        previous_end = segment.test_end
    return CompoundedOOSSeries(
        points=points,
        compounded_return_pct=(growth - 1.0) * PERCENT_SCALE,
        has_gaps=any(point.gap_before for point in points),
    )
