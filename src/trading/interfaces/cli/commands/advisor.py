from __future__ import annotations

import argparse

from trading.interfaces.cli.commands.options import add_account_arg, add_book_arg
from trading.models.advisor import DECIDED_BY_OPERATOR, DECISION_TYPES, DEFAULT_OUTCOME_WINDOW_DAYS


def add_advisor_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_record = sub.add_parser(
        "advisor-record",
        help="Record an advisor decision (including hold) with its rationale and frozen evidence.",
    )
    add_account_arg(p_record)
    add_book_arg(p_record)
    p_record.add_argument("--type", required=True, choices=DECISION_TYPES, help="Decision type")
    p_record.add_argument("--rationale", required=True, help="Why this decision was made")
    p_record.add_argument(
        "--decided-by",
        default=DECIDED_BY_OPERATOR,
        help=f"Who made the decision (default: {DECIDED_BY_OPERATOR}; the advisor agent passes 'agent')",
    )
    p_record.add_argument(
        "--strategy",
        default=None,
        help="Catalog strategy the decision puts or keeps in place (default: the book's assigned strategy)",
    )
    p_record.add_argument(
        "--alternative",
        default=None,
        help=(
            "Catalog strategy the decision rejected; scoring backtests both over the following window. "
            "Omit for disable_strategy and run_experiment."
        ),
    )
    p_record.add_argument(
        "--note",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra evidence to freeze with the decision; repeatable",
    )
    p_record.add_argument("--experiment-id", type=int, default=None, help="Walk-forward experiment the decision cites")
    p_record.add_argument("--promotion-review-id", type=int, default=None, help="Promotion review the decision cites")
    p_record.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_OUTCOME_WINDOW_DAYS,
        help=f"Trading days before the outcome is scored (default: {DEFAULT_OUTCOME_WINDOW_DAYS})",
    )

    p_digest = sub.add_parser(
        "advisor-digest",
        help="Show each account's evaluation, recent decisions, and review flags. Read-only.",
    )
    p_digest.add_argument("--account", default=None, help="Limit to one account (default: all accounts)")
    p_digest.add_argument(
        "--as-of",
        default=None,
        help="Trading date YYYY-MM-DD that decides which decisions are due (default: today, UTC)",
    )

    p_score = sub.add_parser(
        "advisor-score",
        help=(
            "Score decisions whose outcome window has closed: backtest the chosen and rejected strategies "
            "over the window that followed and record the verdict."
        ),
    )
    p_score.add_argument("--account", default=None, help="Limit to one account (default: all accounts)")
    p_score.add_argument(
        "--as-of",
        default=None,
        help="Trading date YYYY-MM-DD that decides which decisions are due (default: today, UTC)",
    )
