from __future__ import annotations

import argparse


def int_or_none(raw: str) -> int | None:
    """Argparse type for nullable integer settings: pass 'none' to clear."""
    if raw.strip().lower() == "none":
        return None
    return int(raw)


def float_or_none(raw: str) -> float | None:
    """Argparse type for nullable float settings: pass 'none' to clear."""
    if raw.strip().lower() == "none":
        return None
    return float(raw)


def add_settings_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_throttle = sub.add_parser(
        "configure-throttle",
        help="Edit the global trade throttle (omitted flags keep their current values; pass 'none' to clear).",
    )
    p_throttle.add_argument(
        "--max-trades-per-day",
        type=int_or_none,
        default=argparse.SUPPRESS,
        help="Max trades per day, or 'none' for unlimited",
    )
    p_throttle.add_argument(
        "--max-trades-per-minute",
        type=int_or_none,
        default=argparse.SUPPRESS,
        help="Max trades per minute, or 'none' for unlimited",
    )

    p_evaluation = sub.add_parser(
        "configure-evaluation",
        help="Edit global evaluation confidence settings (omitted flags keep their current values).",
    )
    p_evaluation.add_argument("--backtest-trade-count-for-full-confidence", type=int, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--backtest-snapshot-count-for-full-confidence", type=int, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--paper-live-snapshot-count-for-full-confidence", type=int, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--backtest-trade-confidence-weight", type=float, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--backtest-snapshot-confidence-weight", type=float, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--backtest-evidence-weight", type=float, default=argparse.SUPPRESS)
    p_evaluation.add_argument("--paper-live-evidence-weight", type=float, default=argparse.SUPPRESS)

    p_rotation_policy = sub.add_parser(
        "configure-book-rotation-policy",
        help=(
            "Edit a book's rotation policy (P7: weights, threshold, cooldown, min-trades)."
            " Omitted flags keep their current values; pass 'none' to fall back to the code default."
        ),
    )
    p_rotation_policy.add_argument("--account", required=True, help="Account name")
    p_rotation_policy.add_argument("--book", default=None, help="Book name (default: the account's default book)")
    p_rotation_policy.add_argument("--min-trades-in-window", type=int_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--outperformance-threshold-bps", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--cooldown-days", type=int_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--risk-adjusted-return-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--stability-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--drawdown-penalty-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--cost-penalty-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--regime-fit-weight", type=float_or_none, default=argparse.SUPPRESS)

    p_promotion = sub.add_parser(
        "configure-promotion",
        help="Edit global promotion policy settings (omitted flags keep their current values).",
    )
    p_promotion.add_argument("--min-research-backtest-trade-count", type=int, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-research-backtest-snapshot-count", type=int, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-research-backtest-return-pct", type=float, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-research-max-drawdown-pct", type=float, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-research-walk-forward-average-return-pct", type=float, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-live-paper-snapshot-count", type=int, default=argparse.SUPPRESS)
    p_promotion.add_argument("--min-live-overall-confidence", type=float, default=argparse.SUPPRESS)
