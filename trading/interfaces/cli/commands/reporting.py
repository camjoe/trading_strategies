from __future__ import annotations

import argparse


def add_reporting_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_trade = sub.add_parser("trade", help="Record a mock buy or sell.")
    p_trade.add_argument("--account", required=True, help="Account name")
    p_trade.add_argument("--side", required=True, choices=["buy", "sell"], help="Order side")
    p_trade.add_argument("--ticker", required=True, help="Ticker symbol")
    p_trade.add_argument("--qty", type=float, required=True, help="Trade quantity")
    p_trade.add_argument("--price", type=float, required=True, help="Execution price")
    p_trade.add_argument("--fee", type=float, default=0.0, help="Optional trading fee")
    p_trade.add_argument("--time", default=None, help="Optional trade time (ISO string)")
    p_trade.add_argument("--note", default=None, help="Optional trade note")

    p_report = sub.add_parser("report", help="Show account status and open positions.")
    p_report.add_argument("--account", required=True, help="Account name")

    p_promotion = sub.add_parser(
        "promotion-status",
        help="Show read-only promotion readiness based on the canonical evaluation artifact.",
    )
    p_promotion.add_argument("--account", required=True, help="Account name")
    p_promotion.add_argument("--strategy", default=None, help="Optional strategy override")

    p_request_review = sub.add_parser(
        "promotion-request-review",
        help="Persist the current promotion assessment as a manual review request.",
    )
    p_request_review.add_argument("--account", required=True, help="Account name")
    p_request_review.add_argument("--strategy", default=None, help="Optional strategy override")
    p_request_review.add_argument("--requested-by", default=None, help="Optional operator name")
    p_request_review.add_argument("--note", default=None, help="Optional request note")

    p_review_history = sub.add_parser(
        "promotion-review-history",
        help="Show persisted promotion review requests and audit events.",
    )
    p_review_history.add_argument("--account", required=True, help="Account name")
    p_review_history.add_argument("--strategy", default=None, help="Optional strategy filter")
    p_review_history.add_argument("--limit", type=int, default=10, help="Number of reviews to show")

    p_review_action = sub.add_parser(
        "promotion-review-action",
        help="Approve, reject, or annotate an open promotion review request.",
    )
    p_review_action.add_argument("--review-id", type=int, required=True, help="Promotion review id")
    p_review_action.add_argument(
        "--action",
        required=True,
        choices=["approve", "reject", "note"],
        help="Review action to record",
    )
    p_review_action.add_argument("--actor", default=None, help="Optional operator name")
    p_review_action.add_argument("--note", default=None, help="Optional action note")

    p_snapshot = sub.add_parser("snapshot", help="Save equity snapshot for an account.")
    p_snapshot.add_argument("--account", required=True, help="Account name")
    p_snapshot.add_argument("--time", default=None, help="Optional snapshot time (ISO string)")

    p_history = sub.add_parser("snapshot-history", help="Show account snapshot history.")
    p_history.add_argument("--account", required=True, help="Account name")
    p_history.add_argument("--limit", type=int, default=20, help="Number of rows to show")

    p_compare = sub.add_parser(
        "compare-strategies",
        help="Compare current paper accounts by account policy state, holdings, benchmark, and trend (not canonical research scores).",
    )
    p_compare.add_argument(
        "--lookback",
        type=int,
        default=10,
        help="Snapshot lookback count for trend classification (default: 10)",
    )
