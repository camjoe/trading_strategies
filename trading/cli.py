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
        "--risk-policy",
        default="none",
        choices=["none", "fixed_stop", "take_profit", "stop_and_target"],
        help="Risk management policy",
    )
    p_create.add_argument("--stop-loss-pct", type=float, default=None, help="Stop-loss percent")
    p_create.add_argument("--take-profit-pct", type=float, default=None, help="Take-profit percent")
    p_create.add_argument(
        "--instrument-mode",
        default="equity",
        choices=["equity", "leaps"],
        help="Execution style: equity shares or LEAPs-style simulation",
    )
    p_create.add_argument(
        "--option-strike-offset-pct",
        type=float,
        default=None,
        help="Option strike offset percent vs underlying (for LEAPs simulation)",
    )
    p_create.add_argument("--option-min-dte", type=int, default=None, help="Minimum days-to-expiration")
    p_create.add_argument("--option-max-dte", type=int, default=None, help="Maximum days-to-expiration")
    p_create.add_argument(
        "--option-type",
        default=None,
        choices=["call", "put", "both"],
        help="Preferred option type for options-style trading",
    )
    p_create.add_argument("--target-delta-min", type=float, default=None, help="Minimum target option delta (0-1)")
    p_create.add_argument("--target-delta-max", type=float, default=None, help="Maximum target option delta (0-1)")
    p_create.add_argument("--max-premium-per-trade", type=float, default=None, help="Max option premium budget per trade")
    p_create.add_argument("--max-contracts-per-trade", type=int, default=None, help="Maximum option contracts per trade")
    p_create.add_argument("--iv-rank-min", type=float, default=None, help="Minimum IV rank threshold (0-100)")
    p_create.add_argument("--iv-rank-max", type=float, default=None, help="Maximum IV rank threshold (0-100)")
    p_create.add_argument("--roll-dte-threshold", type=int, default=None, help="Roll position when DTE <= threshold")
    p_create.add_argument("--profit-take-pct", type=float, default=None, help="Profit target percent")
    p_create.add_argument("--max-loss-pct", type=float, default=None, help="Maximum tolerated loss percent")
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
    p_configure.add_argument(
        "--risk-policy",
        default=None,
        choices=["none", "fixed_stop", "take_profit", "stop_and_target"],
        help="Risk management policy",
    )
    p_configure.add_argument("--stop-loss-pct", type=float, default=None, help="Stop-loss percent")
    p_configure.add_argument("--take-profit-pct", type=float, default=None, help="Take-profit percent")
    p_configure.add_argument(
        "--instrument-mode",
        default=None,
        choices=["equity", "leaps"],
        help="Execution style: equity shares or LEAPs-style simulation",
    )
    p_configure.add_argument(
        "--option-strike-offset-pct",
        type=float,
        default=None,
        help="Option strike offset percent vs underlying (for LEAPs simulation)",
    )
    p_configure.add_argument("--option-min-dte", type=int, default=None, help="Minimum days-to-expiration")
    p_configure.add_argument("--option-max-dte", type=int, default=None, help="Maximum days-to-expiration")
    p_configure.add_argument(
        "--option-type",
        default=None,
        choices=["call", "put", "both"],
        help="Preferred option type for options-style trading",
    )
    p_configure.add_argument("--target-delta-min", type=float, default=None, help="Minimum target option delta (0-1)")
    p_configure.add_argument("--target-delta-max", type=float, default=None, help="Maximum target option delta (0-1)")
    p_configure.add_argument("--max-premium-per-trade", type=float, default=None, help="Max option premium budget per trade")
    p_configure.add_argument("--max-contracts-per-trade", type=int, default=None, help="Maximum option contracts per trade")
    p_configure.add_argument("--iv-rank-min", type=float, default=None, help="Minimum IV rank threshold (0-100)")
    p_configure.add_argument("--iv-rank-max", type=float, default=None, help="Maximum IV rank threshold (0-100)")
    p_configure.add_argument("--roll-dte-threshold", type=int, default=None, help="Roll position when DTE <= threshold")
    p_configure.add_argument("--profit-take-pct", type=float, default=None, help="Profit target percent")
    p_configure.add_argument("--max-loss-pct", type=float, default=None, help="Maximum tolerated loss percent")

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

    p_apply_profiles = sub.add_parser(
        "apply-account-profiles",
        help="Create/update accounts from a JSON profile file.",
    )
    p_apply_profiles.add_argument(
        "--file",
        default="trading/account_profiles/default.json",
        help="Path to JSON account profile file (default: trading/account_profiles/default.json)",
    )
    p_apply_profiles.add_argument(
        "--no-create-missing",
        action="store_true",
        help="Do not create accounts that do not already exist",
    )

    p_apply_preset = sub.add_parser(
        "apply-account-preset",
        help="Apply a built-in account profile preset.",
    )
    p_apply_preset.add_argument(
        "--preset",
        required=True,
        choices=["aggressive", "conservative"],
        help="Preset name to apply",
    )
    p_apply_preset.add_argument(
        "--no-create-missing",
        action="store_true",
        help="Do not create accounts that do not already exist",
    )

    p_backtest = sub.add_parser(
        "backtest",
        help="Run a historical backtest for an existing account configuration.",
    )
    p_backtest.add_argument("--account", required=True, help="Account name")
    p_backtest.add_argument(
        "--tickers-file",
        default="trading/trade_universe.txt",
        help="Path to ticker universe file (default: trading/trade_universe.txt)",
    )
    p_backtest.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p_backtest.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_backtest.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
    p_backtest.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    p_backtest.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    p_backtest.add_argument("--run-name", default=None, help="Optional run label")
    p_backtest.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )

    p_backtest_report = sub.add_parser(
        "backtest-report",
        help="Show summary metrics for a previous backtest run.",
    )
    p_backtest_report.add_argument("--run-id", type=int, required=True, help="Backtest run id")

    return parser
