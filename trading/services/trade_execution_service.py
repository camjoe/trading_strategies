from __future__ import annotations

import random
import sqlite3
from typing import Callable, Mapping, Protocol, cast

from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.utils.coercion import row_expect_int, row_float, row_int


class AccountStateLike(Protocol):
    positions: Mapping[str, float]


class TradePreparationStateLike(AccountStateLike, Protocol):
    cash: float


def _account_value(account: dict[str, object], key: str) -> object | None:
    try:
        return account[key]
    except (KeyError, IndexError):
        return None


def _position_mark_price(
    ticker: str,
    *,
    prices: dict[str, float],
    avg_cost: Mapping[str, float],
    instrument_mode: str,
    trade_price: float | None = None,
) -> float:
    if instrument_mode == "leaps":
        if trade_price is not None:
            return float(trade_price)
        return float(avg_cost.get(ticker, 0.0))

    market_price = prices.get(ticker)
    if market_price is not None and market_price > 0:
        return float(market_price)
    return float(avg_cost.get(ticker, 0.0))


def _estimate_portfolio_equity(
    state: TradePreparationStateLike,
    *,
    prices: dict[str, float],
    instrument_mode: str,
    trade_ticker: str | None = None,
    trade_price: float | None = None,
) -> float:
    positions = cast(Mapping[str, float], getattr(state, "positions", {}))
    avg_cost = cast(Mapping[str, float], getattr(state, "avg_cost", {}))
    equity = float(state.cash)
    for held_ticker, qty in positions.items():
        if qty <= 0:
            continue
        mark_price = _position_mark_price(
            held_ticker,
            prices=prices,
            avg_cost=avg_cost,
            instrument_mode=instrument_mode,
            trade_price=trade_price if held_ticker == trade_ticker else None,
        )
        if mark_price <= 0:
            continue
        equity += float(qty) * mark_price
    return equity


def _current_position_value(
    state: TradePreparationStateLike,
    ticker: str,
    *,
    prices: dict[str, float],
    instrument_mode: str,
    trade_price: float,
) -> float:
    positions = cast(Mapping[str, float], getattr(state, "positions", {}))
    qty = float(positions.get(ticker, 0.0))
    if qty <= 0:
        return 0.0
    avg_cost = cast(Mapping[str, float], getattr(state, "avg_cost", {}))
    mark_price = _position_mark_price(
        ticker,
        prices=prices,
        avg_cost=avg_cost,
        instrument_mode=instrument_mode,
        trade_price=trade_price,
    )
    return qty * mark_price


def refresh_account_state(
    conn: sqlite3.Connection,
    account: dict[str, object],
    *,
    compute_account_state_fn: Callable[[float, list[dict[str, object]]], object],
    load_trades_fn: Callable[[sqlite3.Connection, int], list[dict[str, object]]],
):
    return compute_account_state_fn(row_float(account, "initial_cash") or 0.0, load_trades_fn(conn, row_expect_int(account, "id")))


def prepare_trade_selection(
    account: dict[str, object],
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
    *,
    choose_side_fn: Callable[[str | None, list[str], str | None], str],
    prepare_buy_trade_fn: Callable[..., tuple[str, int, float, float | None, float | None] | None],
    prepare_sell_trade_fn: Callable[..., tuple[str, int, float] | None],
) -> tuple[str, str, int, float, float | None, float | None] | None:
    side = choose_side_fn(forced_sell, can_sell, active_strategy)

    delta_est: float | None = None
    iv_est: float | None = None

    if side == "buy":
        prepared_buy = prepare_buy_trade_fn(
            account,
            instrument_mode,
            universe,
            prices,
            iv_rank_proxy,
            state,
            learning_enabled,
            fee,
        )
        if prepared_buy is None:
            return None
        ticker, qty, trade_price, delta_est, iv_est = prepared_buy
    else:
        prepared_sell = prepare_sell_trade_fn(
            can_sell,
            forced_sell,
            prices,
            state,
            learning_enabled,
            instrument_mode,
        )
        if prepared_sell is None:
            return None
        ticker, qty, trade_price = prepared_sell

    return side, ticker, qty, trade_price, delta_est, iv_est


def record_prepared_trade(
    conn: sqlite3.Connection,
    account_name: str,
    account: dict[str, object],
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection: tuple[str, str, int, float, float | None, float | None],
    forced_sell: str | None,
    *,
    record_trade_fn: Callable[..., None],
    utc_now_iso_fn: Callable[[], str],
    build_trade_note_fn: Callable[..., str],
    trade_time_iso: str | None = None,
) -> None:
    side, ticker, qty, trade_price, delta_est, iv_est = selection
    record_trade_fn(
        conn,
        account_name=account_name,
        side=side,
        ticker=ticker,
        qty=qty,
        price=trade_price,
        fee=fee,
        trade_time=trade_time_iso or utc_now_iso_fn(),
        note=build_trade_note_fn(
            learning_enabled,
            forced_sell,
            risk_policy,
            instrument_mode,
            account,
            side,
            delta_est,
            iv_est,
            active_strategy,
        ),
    )


def build_leaps_candidates(
    account: dict[str, object],
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    *,
    option_candidate_allowed_fn: Callable[[dict[str, object], str, float, dict[str, float]], tuple[bool, float, float]],
) -> list[tuple[str, float, float]]:
    candidates: list[tuple[str, float, float]] = []
    for ticker in universe:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        ok, delta_est, iv_est = option_candidate_allowed_fn(
            account,
            ticker,
            float(price),
            iv_rank_proxy,
        )
        if ok:
            candidates.append((ticker, delta_est, iv_est))

    return candidates


def prepare_buy_trade(
    account: dict[str, object],
    instrument_mode: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: TradePreparationStateLike,
    learning_enabled: bool,
    fee: float,
    *,
    build_leaps_candidates_fn: Callable[[dict[str, object], list[str], dict[str, float], dict[str, float]], list[tuple[str, float, float]]],
    estimate_option_premium_fn: Callable[[float, float, int | None, int | None], float],
    choose_buy_qty_fn: Callable[..., int],
    apply_leaps_buy_qty_limits_fn: Callable[[int, float, dict[str, object]], int],
    choose_buy_ticker_fn: Callable[[list[str], dict[str, float], object, bool], str],
) -> tuple[str, int, float, float | None, float | None] | None:
    if instrument_mode == "leaps":
        candidates = build_leaps_candidates_fn(account, universe, prices, iv_rank_proxy)
        if not candidates:
            return None

        ticker, delta_est, iv_est = random.choice(candidates)
        price = prices.get(ticker)
        if price is None or price <= 0:
            return None

        option_price = estimate_option_premium_fn(
            float(price),
            delta_est,
            row_int(account, "option_min_dte"),
            row_int(account, "option_max_dte"),
        )
        qty = choose_buy_qty_fn(
            state.cash,
            option_price,
            fee,
            trade_size_pct=_account_value(account, "trade_size_pct"),
            max_position_pct=_account_value(account, "max_position_pct"),
            current_position_value=_current_position_value(
                state,
                ticker,
                prices=prices,
                instrument_mode=instrument_mode,
                trade_price=float(option_price),
            ),
            portfolio_equity=_estimate_portfolio_equity(
                state,
                prices=prices,
                instrument_mode=instrument_mode,
                trade_ticker=ticker,
                trade_price=float(option_price),
            ),
        )
        if qty <= 0:
            return None

        qty = apply_leaps_buy_qty_limits_fn(qty, option_price, account)
        if qty <= 0:
            return None

        return ticker, qty, float(option_price), delta_est, iv_est

    ticker = choose_buy_ticker_fn(universe, prices, state, learning_enabled)
    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_buy_qty_fn(
        state.cash,
        float(price),
        fee,
        trade_size_pct=_account_value(account, "trade_size_pct"),
        max_position_pct=_account_value(account, "max_position_pct"),
        current_position_value=_current_position_value(
            state,
            ticker,
            prices=prices,
            instrument_mode=instrument_mode,
            trade_price=float(price),
        ),
        portfolio_equity=_estimate_portfolio_equity(
            state,
            prices=prices,
            instrument_mode=instrument_mode,
            trade_ticker=ticker,
            trade_price=float(price),
        ),
    )
    if qty <= 0:
        return None

    return ticker, qty, float(price), None, None


def prepare_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state: AccountStateLike,
    learning_enabled: bool,
    instrument_mode: str,
    *,
    choose_sell_ticker_fn: Callable[[list[str], dict[str, float], object, bool], str],
    choose_sell_qty_fn: Callable[[float], int],
) -> tuple[str, int, float] | None:
    if forced_sell is not None:
        ticker = forced_sell
    else:
        ticker = choose_sell_ticker_fn(can_sell, prices, state, learning_enabled)

    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = choose_sell_qty_fn(state.positions[ticker])
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
    *,
    get_account_fn: Callable[[sqlite3.Connection, str], dict[str, object]],
    utc_now_iso_fn: Callable[[], str],
    rotate_account_if_due_fn: Callable[[sqlite3.Connection, str, dict[str, object], str], dict[str, object]],
    resolve_active_strategy_fn: Callable[[dict[str, object]], str],
    refresh_account_state_fn: Callable[[sqlite3.Connection, dict[str, object]], AccountStateLike],
    resolve_forced_sell_ticker_fn: Callable[..., str | None],
    prepare_trade_selection_fn: Callable[..., tuple[str, str, int, float, float | None, float | None] | None],
    record_prepared_trade_fn: Callable[..., None],
    enforce_runtime_trade_throttles_fn: Callable[..., None],
) -> int:
    account = get_account_fn(conn, account_name)
    now_iso = utc_now_iso_fn()
    account = rotate_account_if_due_fn(conn, account_name, account, now_iso)
    active_strategy = resolve_active_strategy_fn(account)
    learning_enabled = bool(
        int(cast(int | float | str | bytes | bytearray, account["learning_enabled"] or 0))
    )
    risk_policy = str(account["risk_policy"]).strip().lower()
    stop_loss_pct = account["stop_loss_pct"]
    take_profit_pct = account["take_profit_pct"]
    instrument_mode = str(account["instrument_mode"]).strip().lower()
    target = random.randint(min_trades, max_trades)
    executed = 0
    for _ in range(target):
        state = refresh_account_state_fn(conn, account)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sell = resolve_forced_sell_ticker_fn(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )

        selection = prepare_trade_selection_fn(
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
        )
        if selection is None:
            continue

        trade_time_iso = utc_now_iso_fn()
        try:
            enforce_runtime_trade_throttles_fn(
                conn,
                trade_time_iso=trade_time_iso,
            )
            record_prepared_trade_fn(
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
                trade_time_iso=trade_time_iso,
            )
        except RuntimeTradeThrottleExceededError:
            break
        executed += 1

    return executed
