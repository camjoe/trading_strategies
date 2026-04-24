import argparse
import random

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import ensure_db
from trading.services.auto_trading import (
    resolve_account_names as resolve_account_names_impl,
    resolve_market_inputs as resolve_market_inputs_impl,
    run_accounts as run_accounts_impl,
    run_for_account,
    validate_trade_count_range as validate_trade_count_range_impl,
)
from trading.services.profile_source import DEFAULT_TICKERS_FILE

REPO_ROOT = get_repo_root(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute 1-5 simulated daily paper trades per account."
    )
    parser.add_argument(
        "--accounts",
        required=True,
        help="Comma-separated account names, e.g. momentum_5k,meanrev_5k",
    )
    parser.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    parser.add_argument("--min-trades", type=int, default=1, help="Minimum trades per account")
    parser.add_argument("--max-trades", type=int, default=5, help="Maximum trades per account")
    parser.add_argument("--fee", type=float, default=0.0, help="Per-trade fee")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    return parser.parse_args()
def main() -> None:
    args = parse_args()
    validate_trade_count_range_impl(args.min_trades, args.max_trades)

    if args.seed is not None:
        random.seed(args.seed)

    accounts = resolve_account_names_impl(args.accounts)
    universe, prices, iv_rank_proxy = resolve_market_inputs_impl(args.tickers_file)

    conn = ensure_db()
    try:
        for account_name, executed in run_accounts_impl(
            conn,
            account_names=accounts,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            min_trades=args.min_trades,
            max_trades=args.max_trades,
            fee=args.fee,
        ):
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
