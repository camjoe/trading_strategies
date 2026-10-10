from __future__ import annotations

import argparse

from trading.interfaces.cli.commands.options import add_account_arg, add_book_arg


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


def bool_flag(raw: str) -> bool:
    """Argparse type for explicit true/false flags."""
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {raw!r}")


def schedule_or_none(raw: str) -> list[str] | None:
    """Argparse type for a comma-separated strategy list: pass 'none' to clear."""
    if raw.strip().lower() == "none":
        return None
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise argparse.ArgumentTypeError("expected a comma-separated strategy list or 'none'")
    return names


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
            "Edit a book's rotation policy (weights, threshold, cooldown, min-trades)."
            " Omitted flags keep their current values; pass 'none' to fall back to the code default."
        ),
    )
    add_account_arg(p_rotation_policy)
    add_book_arg(p_rotation_policy)
    p_rotation_policy.add_argument("--min-trades-in-window", type=int_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--outperformance-threshold-bps", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--cooldown-days", type=int_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--risk-adjusted-return-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--stability-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--drawdown-penalty-weight", type=float_or_none, default=argparse.SUPPRESS)
    p_rotation_policy.add_argument("--regime-fit-weight", type=float_or_none, default=argparse.SUPPRESS)

    p_rotation = sub.add_parser(
        "configure-book-rotation",
        help=(
            "Edit a book's rotation scheduling (enabled gate, challenger schedule, lookback)."
            " Omitted flags keep their current values; pass 'none' to clear schedule/lookback."
        ),
    )
    add_account_arg(p_rotation)
    add_book_arg(p_rotation)
    p_rotation.add_argument(
        "--enabled",
        type=bool_flag,
        default=argparse.SUPPRESS,
        help="Whether the book rotates (true/false)",
    )
    p_rotation.add_argument(
        "--schedule",
        type=schedule_or_none,
        default=argparse.SUPPRESS,
        help="Comma-separated challenger strategy names, or 'none' for incumbent-only",
    )
    p_rotation.add_argument(
        "--lookback-days",
        type=int_or_none,
        default=argparse.SUPPRESS,
        help="Evidence lookback window in days, or 'none' for the code default",
    )

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

    p_settings_history = sub.add_parser(
        "settings-history",
        help="Show the global settings change-audit history (throttle, evaluation, promotion edits).",
    )
    p_settings_history.add_argument("--limit", type=int, default=20, help="Number of change events to show")

    p_book_rotation_history = sub.add_parser(
        "book-rotation-history",
        help="Show a book's rotation settings change-audit history (scheduling and policy edits).",
    )
    add_account_arg(p_book_rotation_history)
    add_book_arg(p_book_rotation_history)
    p_book_rotation_history.add_argument("--limit", type=int, default=20, help="Number of change events to show")
