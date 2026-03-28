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
from trading.services.trade_execution_service import (
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
    # IV rank proxy: percentile rank of 1y realized volatility inside the current trade universe.
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            close = get_provider().fetch_close_series(ticker, "1y")
            if close is None or len(close) < 30:
                continue
            daily_ret = close.pct_change().dropna()
            if daily_ret.empty:
                continue
            vol_annual = float(daily_ret.std() * (252 ** 0.5))
            vols[ticker] = vol_annual
        except Exception:
            continue

    if not vols:
        return {}

    sorted_items = sorted(vols.items(), key=lambda x: x[1])
    n = len(sorted_items)
    if n == 1:
        return {sorted_items[0][0]: 50.0}

    out: dict[str, float] = {}
    for i, (ticker, _vol) in enumerate(sorted_items):
        out[ticker] = (i / (n - 1)) * 100.0
    return out


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
    candidates: list[tuple[str, float, float]] = []
    for ticker in universe:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        ok, delta_est, iv_est = option_candidate_allowed(
            account,
            ticker,
            float(price),
            iv_rank_proxy,
        )
        if ok:
            candidates.append((ticker, delta_est, iv_est))

    return candidates


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
    if instrument_mode == "leaps":
        candidates = _build_leaps_candidates(account, universe, prices, iv_rank_proxy)
        if not candidates:
            return None

        ticker, delta_est, iv_est = random.choice(candidates)
        price = prices.get(ticker)
        if price is None or price <= 0:
            return None

        option_price = estimate_option_premium(
            float(price),
            delta_est,
            int(account["option_min_dte"]) if account["option_min_dte"] is not None else None,
            int(account["option_max_dte"]) if account["option_max_dte"] is not None else None,
        )
        qty = choose_buy_qty(state.cash, option_price, fee)
        if qty <= 0:
            return None

        qty = _apply_leaps_buy_qty_limits(qty, option_price, account)
        if qty <= 0:
            return None

        return ticker, qty, float(option_price), delta_est, iv_est

    ticker = choose_buy_ticker(universe, prices, state, learning_enabled)
    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_buy_qty(state.cash, float(price), fee)
    if qty <= 0:
        return None

    return ticker, qty, float(price), None, None


def _prepare_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state: AccountState,
    learning_enabled: bool,
    instrument_mode: str,
) -> SellTradeSelection | None:
    if forced_sell is not None:
        ticker = forced_sell
    else:
        ticker = choose_sell_ticker(can_sell, prices, state, learning_enabled)

    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_sell_qty(state.positions[ticker])
    if qty <= 0:
        return None

    if instrument_mode == "leaps":
        qty = min(qty, 2)

    return ticker, qty, float(price)


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


def main() -> None:
    args = parse_args()
    if args.min_trades < 1:
        raise ValueError("--min-trades must be >= 1")
    if args.max_trades < args.min_trades:
        raise ValueError("--max-trades must be >= --min-trades")

    if args.seed is not None:
        random.seed(args.seed)

    accounts = [a.strip() for a in args.accounts.split(",") if a.strip()]
    if not accounts:
        raise ValueError("No accounts provided.")

    universe = load_tickers_from_file(args.tickers_file)
    if not universe:
        raise ValueError("Ticker universe is empty.")

    prices = fetch_latest_prices(universe)
    if not prices:
        raise ValueError("Could not fetch any prices for ticker universe.")
    iv_rank_proxy = build_iv_rank_proxy(universe)

    conn = ensure_db()
    try:
        for account_name in accounts:
            executed = run_for_account(
                conn=conn,
                account_name=account_name,
                universe=universe,
                prices=prices,
                iv_rank_proxy=iv_rank_proxy,
                min_trades=args.min_trades,
                max_trades=args.max_trades,
                fee=args.fee,
            )
            print(f"{account_name}: executed {executed} trades")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
