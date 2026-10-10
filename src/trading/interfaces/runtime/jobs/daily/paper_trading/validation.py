"""Semantic validation of parsed daily paper-trading arguments.

Each validator returns an operator-facing error message when the input is
invalid, or ``None`` when it passes. Callers print the message to stderr and
exit non-zero; keeping the checks here makes them unit-testable in isolation.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping


def validate_trade_count_args(args: argparse.Namespace) -> str | None:
    if args.shadow_eval_rolling_window_days is not None and args.shadow_eval_rolling_window_days < 1:
        return "--shadow-eval-rolling-window-days must be >= 1"
    if args.primary_max_trades < 1:
        return "--primary-max-trades must be >= 1"
    if args.other_max_trades < 1:
        return "--other-max-trades must be >= 1"
    return None


def validate_account_trade_cap_overrides(
    overrides: Mapping[str, object],
    known_accounts: Iterable[str],
) -> str | None:
    known = set(known_accounts)
    unknown = [name for name in overrides if name not in known]
    if unknown:
        return f"Unknown account(s) in --account-trade-caps: {', '.join(unknown)}"
    return None
