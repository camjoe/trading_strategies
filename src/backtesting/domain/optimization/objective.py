from __future__ import annotations

from collections import Counter
from typing import Any

from backtesting.domain.metrics import calmar_ratio
from backtesting.models.optimizer import CandidateResult
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
