from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionGateResult:
    """Whether a persisted experiment clears the quality bar for promotion.

    ``reasons`` lists every condition that failed (not just the first), so a
    caller can report the whole picture. Empty iff ``passed`` is ``True``.
    """

    passed: bool
    reasons: tuple[str, ...]


def evaluate_promotion_gate(
    *,
    oos_mean_winner_return_pct: float | None,
    oos_mean_baseline_return_pct: float | None,
    oos_windows_beat_baseline: int | None,
    window_count: int,
    holdout_winner_return_pct: float | None,
    holdout_baseline_return_pct: float | None,
) -> PromotionGateResult:
    """Compare the winner against its own default on OOS and holdout evidence.

    Three independent conditions, all required: the winner's mean OOS return beats
    the default's; the winner beats the default in a strict majority of OOS windows
    (a good mean can mask a coin-flip per-window record); and the winner's holdout
    return beats the default's. Missing evidence on either side of a comparison
    fails that condition rather than being skipped — no evidence is not a pass.
    """
    reasons: list[str] = []

    if oos_mean_winner_return_pct is None or oos_mean_baseline_return_pct is None:
        reasons.append("no OOS mean-return evidence")
    elif oos_mean_winner_return_pct <= oos_mean_baseline_return_pct:
        reasons.append(
            f"OOS mean return {oos_mean_winner_return_pct:.2f}% did not beat "
            f"baseline {oos_mean_baseline_return_pct:.2f}%"
        )

    if oos_windows_beat_baseline is None or window_count <= 0:
        reasons.append("no per-window OOS evidence")
    elif oos_windows_beat_baseline <= window_count / 2:
        reasons.append(
            f"winner beat baseline in only {oos_windows_beat_baseline}/{window_count} OOS windows (not a majority)"
        )

    if holdout_winner_return_pct is None or holdout_baseline_return_pct is None:
        reasons.append("no holdout evidence")
    elif holdout_winner_return_pct <= holdout_baseline_return_pct:
        reasons.append(
            f"holdout return {holdout_winner_return_pct:.2f}% did not beat baseline {holdout_baseline_return_pct:.2f}%"
        )

    return PromotionGateResult(passed=not reasons, reasons=tuple(reasons))
