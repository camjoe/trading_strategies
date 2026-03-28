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

    p_snapshot = sub.add_parser("snapshot", help="Save equity snapshot for an account.")
    p_snapshot.add_argument("--account", required=True, help="Account name")
    p_snapshot.add_argument("--time", default=None, help="Optional snapshot time (ISO string)")

    p_history = sub.add_parser("snapshot-history", help="Show account snapshot history.")
    p_history.add_argument("--account", required=True, help="Account name")
    p_history.add_argument("--limit", type=int, default=20, help="Number of rows to show")

    p_compare = sub.add_parser(
        "compare-strategies",
        help="Compare accounts by strategy label, positions, benchmark, and trend.",
    )
    p_compare.add_argument(
        "--lookback",
        type=int,
        default=10,
        help="Snapshot lookback count for trend classification (default: 10)",
    )
