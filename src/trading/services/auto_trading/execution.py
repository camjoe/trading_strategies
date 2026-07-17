"""Execution helpers for auto-trading order selection and recording."""

from __future__ import annotations

import logging
from typing import Callable, Mapping, Protocol, cast

import pandas as pd

from common.coercion import row_int
from trading.domain.strategy_signals import evaluate_signal, resolve_strategy
import trading.domain.auto_trading_policy as auto_trader_policy
from trading.domain.feature_provider import FeatureFetcherSet
from trading.models import AccountRecord

logger = logging.getLogger(__name__)

# Per-ticker feature history for signal evaluation: (strategy_name, ticker) -> frame or None.
FeatureHistoryFn = Callable[[str, str], "pd.DataFrame | None"]

# Alternative-style strategies read external features; map each to its fetcher attribute.
_ALTERNATIVE_FEATURE_FETCHER_ATTRS = {
    "policy_regime": "fetch_policy",
    "news_sentiment": "fetch_news",
    "social_trend_rotation": "fetch_social",
}


class AccountStateLike(Protocol):
    positions: Mapping[str, float]


class TradePreparationStateLike(AccountStateLike, Protocol):
    cash: float


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


def build_feature_history_fn(feature_fetchers: FeatureFetcherSet | None) -> FeatureHistoryFn:
    """Build the per-ticker feature-history lookup used during signal evaluation.

    Only alternative-style strategies receive features; every other style gets ``None``.
    Signal functions read features from the last row only, so the live single-row frame
    matches what backtest evaluation sees for the same date.
    """

    def feature_history_for(strategy_name: str, ticker: str) -> pd.DataFrame | None:
        if feature_fetchers is None:
            return None
        try:
            spec = resolve_strategy(strategy_name)
        except ValueError:
            return None
        if spec.strategy_style != "alternative":
            return None
        fetcher_attr = _ALTERNATIVE_FEATURE_FETCHER_ATTRS.get(spec.strategy_id)
        fetcher = getattr(feature_fetchers, fetcher_attr, None) if fetcher_attr else None
        if fetcher is None:
            return None
        try:
            bundle = fetcher(ticker)
        except Exception as exc:
            logger.warning("Feature fetch failed for %s/%s: %s", strategy_name, ticker, exc, exc_info=True)
            return None
        if bundle is None:
            return None
        return bundle.to_feature_row()

    return feature_history_for


def select_signal_trade_candidates(
    strategy_name: str,
    params: Mapping[str, object],
    universe: list[str],
    histories: Mapping[str, pd.Series],
    positions: Mapping[str, float],
    feature_history_fn: FeatureHistoryFn | None = None,
) -> tuple[list[str], list[str]]:
    """Evaluate the strategy's signal per ticker and return (buy, sell) candidates.

    Buys are signaled tickers not already held; sells are signaled tickers held.
    Missing history is treated as hold; too-short history holds inside the
    signal functions themselves.
    """
    held = {ticker for ticker, qty in positions.items() if qty >= 1}
    buy_candidates: list[str] = []
    sell_candidates: list[str] = []
    for ticker in universe:
        history = histories.get(ticker)
        if history is None or history.empty:
            continue
        feature_history = feature_history_fn(strategy_name, ticker) if feature_history_fn is not None else None
        signal = evaluate_signal(strategy_name, history, params, feature_history)
        if signal == "buy" and ticker not in held:
            buy_candidates.append(ticker)
        elif signal == "sell" and ticker in held:
            sell_candidates.append(ticker)
    return buy_candidates, sell_candidates


def prepare_trade_selection(
    account: AccountRecord,
    active_strategy: str | None,
    params: Mapping[str, object] | None,
    state,
    forced_sell: str | None,
    universe: list[str],
    prices: dict[str, float],
    histories: Mapping[str, pd.Series],
    iv_rank_proxy: dict[str, float],
    instrument_mode: str,
    fee: float,
    *,
    trade_size_pct: float | None,
    max_position_pct: float | None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> tuple[str, str, int, float, float | None, float | None] | None:
    """Select the next trade from the active strategy's signals.

    ``params`` are the strategy's effective knobs, resolved by the caller from
    the catalog. Sizing knobs (``trade_size_pct``, ``max_position_pct``) are
    book-owned (revision 0004); ``account`` still supplies the option/leaps
    settings until roadmap item A3. Sells take priority (the forced risk-stop
    first, then signaled sells) so cash is freed before buys. Returns None
    when nothing signals — callers must not manufacture a trade in that case.
    """
    buy_candidates: list[str] = []
    sell_candidates: list[str] = []
    if active_strategy and params is not None:
        try:
            buy_candidates, sell_candidates = select_signal_trade_candidates(
                active_strategy,
                params,
                universe,
                histories,
                cast(Mapping[str, float], getattr(state, "positions", {})),
                feature_history_fn,
            )
        except ValueError:
            logger.warning("Unknown strategy %r; holding (no signal trades).", active_strategy)

    if forced_sell is not None or sell_candidates:
        prepared_sell = prepare_sell_trade(
            sell_candidates,
            forced_sell,
            prices,
            state,
            instrument_mode,
        )
        if prepared_sell is not None:
            ticker, qty, trade_price = prepared_sell
            return "sell", ticker, qty, trade_price, None, None

    prepared_buy = prepare_buy_trade(
        account,
        instrument_mode,
        buy_candidates,
        prices,
        iv_rank_proxy,
        state,
        fee,
        trade_size_pct=trade_size_pct,
        max_position_pct=max_position_pct,
    )
    if prepared_buy is None:
        return None
    ticker, qty, trade_price, delta_est, iv_est = prepared_buy
    return "buy", ticker, qty, trade_price, delta_est, iv_est


def _size_buy_for_ticker(
    account: AccountRecord,
    instrument_mode: str,
    ticker: str,
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: TradePreparationStateLike,
    fee: float,
    *,
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> tuple[str, int, float, float | None, float | None] | None:
    """Size a buy for one signaled ticker; None when it cannot be sized (or leaps-blocked)."""
    price = float(prices[ticker])
    if instrument_mode == "leaps":
        ok, delta_est, iv_est = auto_trader_policy.option_candidate_allowed(
            account,
            ticker,
            iv_rank_proxy,
        )
        if not ok:
            return None
        trade_price = float(
            auto_trader_policy.estimate_option_premium(
                price,
                delta_est,
                row_int(account, "option_min_dte"),
                row_int(account, "option_max_dte"),
            )
        )
    else:
        delta_est = None
        iv_est = None
        trade_price = price

    qty = auto_trader_policy.choose_buy_qty(
        state.cash,
        trade_price,
        fee,
        trade_size_pct=trade_size_pct,
        max_position_pct=max_position_pct,
        current_position_value=_current_position_value(
            state,
            ticker,
            prices=prices,
            instrument_mode=instrument_mode,
            trade_price=trade_price,
        ),
        portfolio_equity=_estimate_portfolio_equity(
            state,
            prices=prices,
            instrument_mode=instrument_mode,
            trade_ticker=ticker,
            trade_price=trade_price,
        ),
    )
    if qty <= 0:
        return None

    if instrument_mode == "leaps":
        qty = auto_trader_policy.apply_leaps_buy_qty_limits(qty, trade_price, account)
        if qty <= 0:
            return None

    return ticker, qty, trade_price, delta_est, iv_est


def prepare_buy_trade(
    account: AccountRecord,
    instrument_mode: str,
    buy_candidates: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: TradePreparationStateLike,
    fee: float,
    *,
    trade_size_pct: float | None,
    max_position_pct: float | None,
) -> tuple[str, int, float, float | None, float | None] | None:
    """Prepare the first sizable buy among the signal-selected candidates, in order."""
    for ticker in buy_candidates:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue
        prepared = _size_buy_for_ticker(
            account,
            instrument_mode,
            ticker,
            prices,
            iv_rank_proxy,
            state,
            fee,
            trade_size_pct=trade_size_pct,
            max_position_pct=max_position_pct,
        )
        if prepared is not None:
            return prepared
    return None


def prepare_sell_trade(
    sell_candidates: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state: AccountStateLike,
    instrument_mode: str,
) -> tuple[str, int, float] | None:
    """Prepare the first sellable ticker: the forced risk-stop first, then signaled sells."""
    ordered = [forced_sell] if forced_sell is not None else []
    ordered.extend(ticker for ticker in sell_candidates if ticker != forced_sell)
    for ticker in ordered:
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        qty = auto_trader_policy.choose_sell_qty(state.positions[ticker])
        if qty <= 0:
            continue

        if instrument_mode == "leaps":
            qty = min(qty, 2)

        return ticker, qty, float(price)
    return None
