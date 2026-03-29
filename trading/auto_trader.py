import argparse
import random
import sqlite3
import sys
from datetime import datetime
from typing import TypeAlias

from common.market_data import get_provider
from common.repo_paths import get_repo_root
from common.tickers import load_tickers_from_file
from common.time import utc_now_iso
from trading.accounting import compute_account_state, load_trades, record_trade
from trading.accounts import get_account
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
from trading.coercion import coerce_float
from trading.database.db import ensure_db
from trading.domain import auto_trader_policy
from trading.models import AccountState
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
    safe_return_pct as safe_return_pct_impl,
    select_optimal_strategy as select_optimal_strategy_impl,
)
from trading.services.auto_trader_service import (
    build_iv_rank_proxy as build_iv_rank_proxy_impl,
    resolve_account_names as resolve_account_names_impl,
    resolve_market_inputs as resolve_market_inputs_impl,
    run_accounts as run_accounts_impl,
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


def choose_buy_qty(cash: float, price: float, fee: float) -> int:
    return auto_trader_policy.choose_buy_qty(cash, price, fee)


def choose_sell_qty(position_qty: float) -> int:
    return auto_trader_policy.choose_sell_qty(position_qty)


def build_iv_rank_proxy(universe: list[str]) -> dict[str, float]:
    return build_iv_rank_proxy_impl(
        universe,
        fetch_close_series_fn=get_provider().fetch_close_series,
    )


def estimate_delta(abs_strike_offset_pct: float) -> float:
    return auto_trader_policy.estimate_delta(abs_strike_offset_pct)


def estimate_option_premium(
    underlying_price: float, delta_est: float, min_dte: int | None, max_dte: int | None
) -> float:
    return auto_trader_policy.estimate_option_premium(
        underlying_price,
        delta_est,
        min_dte,
        max_dte,
    )


def option_candidate_allowed(
    account: sqlite3.Row,
    ticker: str,
    price: float,
    iv_rank_proxy: dict[str, float],
) -> tuple[bool, float, float]:
    return auto_trader_policy.option_candidate_allowed(
        account,
        ticker,
        price,
        iv_rank_proxy,
        estimate_delta_fn=estimate_delta,
    )


def choose_sell_ticker_by_risk(
    can_sell: list[str],
    prices: dict[str, float],
    state: AccountState,
    risk_policy: str,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> str | None:
    return auto_trader_policy.choose_sell_ticker_by_risk(
        can_sell,
        prices,
        state,
        risk_policy,
        stop_loss_pct,
        take_profit_pct,
    )


def choose_buy_ticker(
    universe: list[str], prices: dict[str, float], state: AccountState, learning_enabled: bool
) -> str:
    return auto_trader_policy.choose_buy_ticker(universe, prices, state, learning_enabled)


def choose_sell_ticker(
    can_sell: list[str], prices: dict[str, float], state: AccountState, learning_enabled: bool
) -> str:
    return auto_trader_policy.choose_sell_ticker(can_sell, prices, state, learning_enabled)


BuyTradeSelection: TypeAlias = tuple[str, int, float, float | None, float | None]
SellTradeSelection: TypeAlias = tuple[str, int, float]


def _refresh_account_state(conn: sqlite3.Connection, account: sqlite3.Row) -> AccountState:
    return refresh_account_state_impl(
        conn,
        account,
        compute_account_state_fn=compute_account_state,
        load_trades_fn=load_trades,
    )


def _resolve_forced_sell_ticker(
    can_sell: list[str],
    prices: dict[str, float],
    state: AccountState,
    risk_policy: str,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
) -> str | None:
    return choose_sell_ticker_by_risk(
        can_sell,
        prices,
        state,
        risk_policy,
        stop_loss_pct,
        take_profit_pct,
    )


def _prepare_trade_selection(
    account: sqlite3.Row,
    active_strategy: str | None,
    state: AccountState,
    can_sell: list[str],
    forced_sell: str | None,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    learning_enabled: bool,
    instrument_mode: str,
    fee: float,
) -> tuple[str, str, int, float, float | None, float | None] | None:
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
        choose_side_fn=_choose_side,
        prepare_buy_trade_fn=_prepare_buy_trade,
        prepare_sell_trade_fn=_prepare_sell_trade,
    )


def _record_prepared_trade(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection: tuple[str, str, int, float, float | None, float | None],
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
        build_trade_note_fn=_build_trade_note,
    )


def _build_leaps_candidates(
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
        option_candidate_allowed_fn=option_candidate_allowed,
    )


def _apply_leaps_buy_qty_limits(
    qty: int,
    option_price: float,
    account: sqlite3.Row,
) -> int:
    return auto_trader_policy.apply_leaps_buy_qty_limits(qty, option_price, account)


def _build_trade_note(
    learning_enabled: bool,
    forced_sell: str | None,
    risk_policy: str,
    instrument_mode: str,
    account: sqlite3.Row,
    side: str,
    delta_est: float | None,
    iv_est: float | None,
    strategy_name: str | None,
) -> str:
    return auto_trader_policy.build_trade_note(
        learning_enabled,
        forced_sell,
        risk_policy,
        instrument_mode,
        account,
        side,
        delta_est,
        iv_est,
        strategy_name,
    )


def _choose_side(forced_sell: str | None, can_sell: list[str], strategy_name: str | None = None) -> str:
    return auto_trader_policy.choose_side(forced_sell, can_sell, strategy_name)


def _rotate_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
) -> sqlite3.Row:
    return rotate_account_if_due_impl(
        conn,
        account_name,
        account,
        now_iso,
        is_rotation_due_fn=lambda row: is_rotation_due(row, as_of_iso=now_iso),
        resolve_rotation_mode_fn=resolve_rotation_mode,
        select_optimal_strategy_fn=_select_optimal_strategy,
        resolve_active_strategy_fn=resolve_active_strategy,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        next_rotation_state_fn=lambda row, as_of: next_rotation_state(row, as_of_iso=as_of),
        update_account_rotation_state_fn=update_account_rotation_state,
        get_account_fn=get_account,
    )


def _parse_as_of_iso(as_of_iso: str) -> datetime:
    return parse_as_of_iso_impl(as_of_iso)


def _safe_return_pct(starting_equity: object, ending_equity: object) -> float | None:
    return safe_return_pct_impl(
        starting_equity,
        ending_equity,
        coerce_float_fn=coerce_float,
    )


def _select_optimal_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
) -> str | None:
    return select_optimal_strategy_impl(
        conn,
        account,
        as_of_iso,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=_parse_as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns,
        resolve_optimality_mode_fn=resolve_optimality_mode,
    )


def _prepare_buy_trade(
    account: sqlite3.Row,
    instrument_mode: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: AccountState,
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
        build_leaps_candidates_fn=_build_leaps_candidates,
        estimate_option_premium_fn=estimate_option_premium,
        choose_buy_qty_fn=choose_buy_qty,
        apply_leaps_buy_qty_limits_fn=_apply_leaps_buy_qty_limits,
        choose_buy_ticker_fn=choose_buy_ticker,
    )


def _prepare_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state: AccountState,
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
        choose_sell_ticker_fn=choose_sell_ticker,
        choose_sell_qty_fn=choose_sell_qty,
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
        rotate_account_if_due_fn=_rotate_account_if_due,
        resolve_active_strategy_fn=resolve_active_strategy,
        refresh_account_state_fn=_refresh_account_state,
        resolve_forced_sell_ticker_fn=_resolve_forced_sell_ticker,
        prepare_trade_selection_fn=_prepare_trade_selection,
        record_prepared_trade_fn=_record_prepared_trade,
    )


def _validate_trade_count_range(min_trades: int, max_trades: int) -> None:
    validate_trade_count_range_impl(min_trades, max_trades)


def _resolve_account_names(accounts_arg: str) -> list[str]:
    return resolve_account_names_impl(accounts_arg)


def _resolve_market_inputs(tickers_file: str) -> tuple[list[str], dict[str, float], dict[str, float]]:
    return resolve_market_inputs_impl(
        tickers_file,
        load_tickers_from_file_fn=load_tickers_from_file,
        fetch_latest_prices_fn=fetch_latest_prices,
        build_iv_rank_proxy_fn=build_iv_rank_proxy,
    )


def _run_accounts(
    conn: sqlite3.Connection,
    account_names: list[str],
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> list[tuple[str, int]]:
    return run_accounts_impl(
        conn,
        account_names=account_names,
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank_proxy,
        min_trades=min_trades,
        max_trades=max_trades,
        fee=fee,
        run_for_account_fn=run_for_account,
    )


def main() -> None:
    args = parse_args()
    _validate_trade_count_range(args.min_trades, args.max_trades)

    if args.seed is not None:
        random.seed(args.seed)

    accounts = _resolve_account_names(args.accounts)
    universe, prices, iv_rank_proxy = _resolve_market_inputs(args.tickers_file)

    conn = ensure_db()
    try:
        for account_name, executed in _run_accounts(
            conn,
            accounts,
            universe,
            prices,
            iv_rank_proxy,
            args.min_trades,
            args.max_trades,
            args.fee,
        ):
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
