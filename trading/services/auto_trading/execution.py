"""Execution helpers for auto-trading order selection and recording."""

from __future__ import annotations

import random
import sqlite3
from typing import Callable, Mapping, Protocol, cast

from common.coercion import row_expect_int, row_float, row_int
from common.time import utc_now_iso
from trading.backtesting.domain.strategy_signals import resolve_strategy
from trading.domain.accounting import compute_account_state
import trading.domain.auto_trader_policy as auto_trader_policy
from trading.domain.exceptions import RuntimeTradeThrottleExceededError
from trading.domain.rotation import resolve_active_strategy
from trading.models import AccountRecord
from trading.services.accounting import list_account_trades
from trading.services.runtime_throttle import enforce_runtime_trade_throttles


class AccountStateLike(Protocol):
    positions: Mapping[str, float]


class TradePreparationStateLike(AccountStateLike, Protocol):
    cash: float


def _account_value(account: AccountRecord, key: str) -> object | None:
    return account.get(key)


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
    account: AccountRecord,
):
    return compute_account_state(
        row_float(account, "initial_cash") or 0.0,
        list_account_trades(conn, row_expect_int(account, "id")),
    )


def _resolve_strategy_style(strategy_name: str | None) -> str | None:
    """Resolve a strategy name to its style for side-selection bias."""
    if not strategy_name:
        return None
    try:
        return resolve_strategy(strategy_name).strategy_style
    except Exception:
        return None


def prepare_trade_selection(
    account: AccountRecord,
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
) -> tuple[str, str, int, float, float | None, float | None] | None:
    side = auto_trader_policy.choose_side(
        forced_sell,
        can_sell,
        _resolve_strategy_style(active_strategy),
    )

    delta_est: float | None = None
    iv_est: float | None = None

    if side == "buy":
        prepared_buy = prepare_buy_trade(
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
        prepared_sell = prepare_sell_trade(
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
    account: AccountRecord,
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection: tuple[str, str, int, float, float | None, float | None],
    forced_sell: str | None,
    *,
    record_trade_fn: Callable[..., None],
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
        trade_time=trade_time_iso or utc_now_iso(),
        note=auto_trader_policy.build_trade_note(
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
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
) -> list[tuple[str, float, float]]:
    candidates: list[tuple[str, float, float]] = []
    for ticker in universe:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        ok, delta_est, iv_est = auto_trader_policy.option_candidate_allowed(
            account,
            ticker,
            iv_rank_proxy,
        )
        if ok:
            candidates.append((ticker, delta_est, iv_est))

    return candidates


def prepare_buy_trade(
    account: AccountRecord,
    instrument_mode: str,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: TradePreparationStateLike,
    learning_enabled: bool,
    fee: float,
) -> tuple[str, int, float, float | None, float | None] | None:
    if instrument_mode == "leaps":
        candidates = build_leaps_candidates(account, universe, prices, iv_rank_proxy)
        if not candidates:
            return None

        ticker, delta_est, iv_est = random.choice(candidates)
        price = prices.get(ticker)
        if price is None or price <= 0:
            return None

        option_price = auto_trader_policy.estimate_option_premium(
            float(price),
            delta_est,
            row_int(account, "option_min_dte"),
            row_int(account, "option_max_dte"),
        )
        qty = auto_trader_policy.choose_buy_qty(
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

        qty = auto_trader_policy.apply_leaps_buy_qty_limits(qty, option_price, account)
        if qty <= 0:
            return None

        return ticker, qty, float(option_price), delta_est, iv_est

    ticker = auto_trader_policy.choose_buy_ticker(universe, prices, state, learning_enabled)
    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = auto_trader_policy.choose_buy_qty(
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
) -> tuple[str, int, float] | None:
    if forced_sell is not None:
        ticker = forced_sell
    else:
        ticker = auto_trader_policy.choose_sell_ticker(can_sell, prices, state, learning_enabled)

    price = prices.get(ticker)
    if price is None or price <= 0:
        return None

    qty = auto_trader_policy.choose_sell_qty(state.positions[ticker])
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
    get_account_fn: Callable[[sqlite3.Connection, str], AccountRecord],
    utc_now_iso_fn: Callable[[], str],
    rotate_account_if_due_fn: Callable[[sqlite3.Connection, str, AccountRecord, str], AccountRecord],
    record_prepared_trade_fn: Callable[..., None],
    is_submission_window_open_fn: Callable[[str], bool],
) -> int:
    account = get_account_fn(conn, account_name)
    now_iso = utc_now_iso_fn()
    if not is_submission_window_open_fn(now_iso):
        return 0
    account = rotate_account_if_due_fn(conn, account_name, account, now_iso)
    active_strategy = resolve_active_strategy(account)
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
        if not is_submission_window_open_fn(utc_now_iso_fn()):
            break
        state = refresh_account_state(conn, account)
        can_sell = [ticker for ticker, qty in state.positions.items() if qty >= 1]
        forced_sell = auto_trader_policy.choose_sell_ticker_by_risk(
            can_sell,
            prices,
            state,
            risk_policy,
            stop_loss_pct,
            take_profit_pct,
        )

        selection = prepare_trade_selection(
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
            enforce_runtime_trade_throttles(
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
