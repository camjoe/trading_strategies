import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Paper trading accounts per strategy with trade and equity tracking."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize paper trading database.")
    sub.add_parser("list-accounts", help="List all paper trading accounts.")

    p_create = sub.add_parser("create-account", help="Create a new paper account.")
    p_create.add_argument("--name", required=True, help="Account name, e.g. trend_v1")
    p_create.add_argument("--display-name", default=None, help="Human-friendly account name")
    p_create.add_argument("--strategy", required=True, help="Strategy label")
    p_create.add_argument("--initial-cash", type=float, required=True, help="Starting cash")
    p_create.add_argument("--goal-min-return-pct", type=float, default=None, help="Goal minimum return percent")
    p_create.add_argument("--goal-max-return-pct", type=float, default=None, help="Goal maximum return percent")
    p_create.add_argument(
        "--goal-period",
        default="monthly",
        help="Goal time period label, e.g. weekly, monthly, quarterly",
    )
    p_create.add_argument(
        "--learning-enabled",
        action="store_true",
        help="Enable learning mode for this account",
    )
    p_create.add_argument(
        "--benchmark",
        default="SPY",
        help="Benchmark ticker for this strategy account (default: SPY)",
    )

    p_set_benchmark = sub.add_parser("set-benchmark", help="Set benchmark ticker for an account.")
    p_set_benchmark.add_argument("--account", required=True, help="Account name")
    p_set_benchmark.add_argument("--benchmark", required=True, help="Benchmark ticker, e.g. SPY")

    p_configure = sub.add_parser("configure-account", help="Update per-account metadata and goals.")
    p_configure.add_argument("--account", required=True, help="Account name")
    p_configure.add_argument("--display-name", default=None, help="Human-friendly account name")
    p_configure.add_argument("--goal-min-return-pct", type=float, default=None, help="Goal minimum return percent")
    p_configure.add_argument("--goal-max-return-pct", type=float, default=None, help="Goal maximum return percent")
    p_configure.add_argument(
        "--goal-period",
        default=None,
        help="Goal time period label, e.g. weekly, monthly, quarterly",
    )
    p_configure.add_argument(
        "--learning-enabled",
        action="store_true",
        help="Turn on learning mode for this account",
    )
    p_configure.add_argument(
        "--learning-disabled",
        action="store_true",
        help="Turn off learning mode for this account",
    )

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

    return parser
