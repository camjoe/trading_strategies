import argparse
import random
import sqlite3
import sys
from typing import TypeAlias

from common.market_data import get_provider
from common.repo_paths import get_repo_root
from common.tickers import load_tickers_from_file
from common.time import utc_now_iso
from trading.accounting import compute_account_state, load_trades, record_trade
from trading.accounts import get_account
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
from trading.database.db import ensure_db
from trading.domain import auto_trader_policy
from trading.pricing import fetch_latest_prices
from trading.repositories.rotation_repository import update_account_rotation_state
from trading.rotation import (
    is_rotation_due,
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_optimality_mode,
    resolve_rotation_mode,
)
from trading.services.rotation_service import (
    parse_as_of_iso as parse_as_of_iso_impl,
    rotate_account_if_due as rotate_account_if_due_impl,
    select_optimal_strategy as select_optimal_strategy_impl,
)
from trading.services.auto_trader_service import (
    build_iv_rank_proxy as build_iv_rank_proxy_impl,
    parse_runtime_as_of_iso as parse_runtime_as_of_iso_impl,
    resolve_account_names as resolve_account_names_impl,
    resolve_market_inputs as resolve_market_inputs_impl,
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    run_accounts as run_accounts_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
    validate_trade_count_range as validate_trade_count_range_impl,
)
from trading.services.trade_execution_service import (
    build_leaps_candidates as build_leaps_candidates_impl,
    prepare_buy_trade as prepare_buy_trade_impl,
    prepare_sell_trade as prepare_sell_trade_impl,
    prepare_trade_selection as prepare_trade_selection_impl,
    record_prepared_trade as record_prepared_trade_impl,
    refresh_account_state as refresh_account_state_impl,
    run_for_account as run_for_account_impl,
)

PROJECT_ROOT = get_repo_root(__file__)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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
        default="trading/trade_universe.txt",
        help="Path to ticker universe file (default: trading/trade_universe.txt)",
    )
    parser.add_argument("--min-trades", type=int, default=1, help="Minimum trades per account")
    parser.add_argument("--max-trades", type=int, default=5, help="Maximum trades per account")
    parser.add_argument("--fee", type=float, default=0.0, help="Per-trade fee")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    return parser.parse_args()


def build_iv_rank_proxy(universe: list[str]) -> dict[str, float]:
    return build_iv_rank_proxy_impl(
        universe,
        fetch_close_series_fn=get_provider().fetch_close_series,
    )


BuyTradeSelection: TypeAlias = tuple[str, int, float, float | None, float | None]
SellTradeSelection: TypeAlias = tuple[str, int, float]


def _parse_runtime_as_of_iso(as_of_iso: str):
    return parse_runtime_as_of_iso_impl(
        as_of_iso,
        parse_as_of_iso_fn=parse_as_of_iso_impl,
    )


def _select_runtime_rotation_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
) -> str | None:
    return select_account_rotation_strategy_impl(
        conn,
        account,
        as_of_iso,
        select_optimal_strategy_impl_fn=select_optimal_strategy_impl,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=_parse_runtime_as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    )


def _rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
) -> sqlite3.Row:
    return rotate_runtime_account_if_due_impl(
        conn,
        account_name,
        account,
        now_iso,
        rotate_account_if_due_impl_fn=rotate_account_if_due_impl,
        is_rotation_due_fn=lambda row: is_rotation_due(row, as_of_iso=now_iso),
        resolve_rotation_mode_fn=resolve_rotation_mode,
        select_optimal_strategy_fn=_select_runtime_rotation_strategy,
        resolve_active_strategy_fn=resolve_active_strategy,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        next_rotation_state_fn=lambda row, as_of: next_rotation_state(row, as_of_iso=as_of),
        update_account_rotation_state_fn=update_account_rotation_state,
        get_account_fn=get_account,
    )


def _refresh_runtime_account_state(conn: sqlite3.Connection, account: sqlite3.Row):
    return refresh_account_state_impl(
        conn,
        account,
        compute_account_state_fn=compute_account_state,
        load_trades_fn=load_trades,
    )


def _build_runtime_leaps_candidates(
    account: sqlite3.Row,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
) -> list[tuple[str, float, float]]:
    return build_leaps_candidates_impl(
        account,
        universe,
        prices,
        iv_rank_proxy,
        option_candidate_allowed_fn=lambda candidate_account, ticker, price, proxy: auto_trader_policy.option_candidate_allowed(
            candidate_account,
            ticker,
            price,
            proxy,
            estimate_delta_fn=auto_trader_policy.estimate_delta,
        ),
    )


def _prepare_runtime_buy_trade(
    account: sqlite3.Row,
    instrument_mode: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state,
    learning_enabled: bool,
    fee: float,
) -> BuyTradeSelection | None:
    return prepare_buy_trade_impl(
        account,
        instrument_mode,
        universe,
        prices,
        iv_rank_proxy,
        state,
        learning_enabled,
        fee,
        build_leaps_candidates_fn=_build_runtime_leaps_candidates,
        estimate_option_premium_fn=auto_trader_policy.estimate_option_premium,
        choose_buy_qty_fn=auto_trader_policy.choose_buy_qty,
        apply_leaps_buy_qty_limits_fn=auto_trader_policy.apply_leaps_buy_qty_limits,
        choose_buy_ticker_fn=auto_trader_policy.choose_buy_ticker,
    )


def _prepare_runtime_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state,
    learning_enabled: bool,
    instrument_mode: str,
) -> SellTradeSelection | None:
    return prepare_sell_trade_impl(
        can_sell,
        forced_sell,
        prices,
        state,
        learning_enabled,
        instrument_mode,
        choose_sell_ticker_fn=auto_trader_policy.choose_sell_ticker,
        choose_sell_qty_fn=auto_trader_policy.choose_sell_qty,
    )


def _prepare_runtime_trade_selection(
    account: sqlite3.Row,
    active_strategy: str | None,
    state,
    can_sell: list[str],
    forced_sell: str | None,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    learning_enabled: bool,
    instrument_mode: str,
    fee: float,
):
    return prepare_trade_selection_impl(
        account,
        active_strategy,
        state,
        can_sell,
        forced_sell,
        universe,
        prices,
        iv_rank_proxy,
        learning_enabled,
        instrument_mode,
        fee,
        choose_side_fn=auto_trader_policy.choose_side,
        prepare_buy_trade_fn=_prepare_runtime_buy_trade,
        prepare_sell_trade_fn=_prepare_runtime_sell_trade,
    )


def _record_runtime_trade(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection,
    forced_sell: str | None,
) -> None:
    record_prepared_trade_impl(
        conn,
        account_name,
        account,
        learning_enabled,
        risk_policy,
        instrument_mode,
        active_strategy,
        fee,
        selection,
        forced_sell,
        record_trade_fn=record_trade,
        utc_now_iso_fn=utc_now_iso,
        build_trade_note_fn=auto_trader_policy.build_trade_note,
    )


def run_for_account(
    conn: sqlite3.Connection,
    account_name: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> int:
    return run_for_account_impl(
        conn,
        account_name,
        universe,
        prices,
        iv_rank_proxy,
        min_trades,
        max_trades,
        fee,
        get_account_fn=get_account,
        utc_now_iso_fn=utc_now_iso,
        rotate_account_if_due_fn=_rotate_runtime_account,
        resolve_active_strategy_fn=resolve_active_strategy,
        refresh_account_state_fn=_refresh_runtime_account_state,
        resolve_forced_sell_ticker_fn=auto_trader_policy.choose_sell_ticker_by_risk,
        prepare_trade_selection_fn=_prepare_runtime_trade_selection,
        record_prepared_trade_fn=_record_runtime_trade,
    )


def main() -> None:
    args = parse_args()
    validate_trade_count_range_impl(args.min_trades, args.max_trades)

    if args.seed is not None:
        random.seed(args.seed)

    accounts = resolve_account_names_impl(args.accounts)
    universe, prices, iv_rank_proxy = resolve_market_inputs_impl(
        args.tickers_file,
        load_tickers_from_file_fn=load_tickers_from_file,
        fetch_latest_prices_fn=fetch_latest_prices,
        build_iv_rank_proxy_fn=build_iv_rank_proxy,
    )

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
            run_for_account_fn=run_for_account,
        ):
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
