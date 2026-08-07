"""Execution helpers for auto-trading order selection and recording."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, cast

import pandas as pd

import trading.domain.auto_trading_policy as auto_trader_policy
from common.coercion import coerce_int
from trading.domain.feature_provider import FeatureFetcherSet
from trading.domain.strategies.resolution import evaluate_signal_over_bars, resolve_strategy

logger = logging.getLogger(__name__)

# Per-ticker feature history for signal evaluation: (strategy_name, ticker) -> frame or None.
FeatureHistoryFn = Callable[[str, str], "pd.DataFrame | None"]

# Alternative-style strategies read external features; each registers the fetcher
# it needs here, keyed by strategy id.
#
# **Parked, not dead.** Empty because no alternative-style strategy is currently
# registered: policy_regime, news_sentiment and social_trend_rotation were retired
# so the simpler price-only behaviours could be confirmed first, and entries naming
# them would resolve to nothing. External-feature strategies are expected back
# around 2026-09.
#
# This is the live half of the feature seam. The backtest half is
# `StrategySpec.required_features` feeding `build_feature_bundle`. Wiring a
# strategy needs both, and the two are checked separately:
# `test_proxy_feature_flow` covers the backtest half, and
# `test_selection.py::TestAlternativeFeatureSeam` covers this one — that test
# registers a synthetic alternative strategy end to end, so it doubles as the
# worked example of what a real one has to declare.
_ALTERNATIVE_FEATURE_FETCHER_ATTRS: dict[str, str] = {}


# (side, ticker, qty, price, delta_est, iv_est) — one prepared trade.
TradeSelection = tuple[str, str, int, float, float | None, float | None]


@dataclass
class _WorkingState:
    """A book's cash and holdings part-way through one run.

    The persisted state is frozen; selection is multi-trade, so it needs a
    mutable copy where a sell's proceeds are visible to the buys after it.
    """

    cash: float
    positions: dict[str, float]
    avg_cost: dict[str, float]


class AccountStateLike(Protocol):
    # Read-only: a plain annotation demands an invariant `Mapping`, which the
    # `dict`-holding implementers fail. Same reason as `PositionCostState`.
    @property
    def positions(self) -> Mapping[str, float]: ...


class TradePreparationStateLike(AccountStateLike, Protocol):
    @property
    def cash(self) -> float: ...


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
    histories: Mapping[str, pd.DataFrame],
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
        # One ticker at a time here, so the indicators are built per call rather
        # than hoisted the way the simulation loop does it.
        signal = evaluate_signal_over_bars(strategy_name, history, params, feature_history)
        if signal == "buy" and ticker not in held:
            buy_candidates.append(ticker)
        elif signal == "sell" and ticker in held:
            sell_candidates.append(ticker)
    return buy_candidates, sell_candidates


def prepare_book_trades(
    option_settings: auto_trader_policy.AccountPolicyInput,
    active_strategy: str | None,
    params: Mapping[str, object] | None,
    state,
    forced_sells: list[str],
    universe: list[str],
    prices: dict[str, float],
    histories: Mapping[str, pd.DataFrame],
    iv_rank_proxy: dict[str, float],
    instrument_mode: str,
    fee: float,
    *,
    max_trades: int,
    trade_size_pct: float | None,
    max_position_pct: float | None,
    feature_history_fn: FeatureHistoryFn | None = None,
    selection_seed: str = "",
) -> list[TradeSelection]:
    """Select up to *max_trades* trades from the active strategy's signals.

    ``params`` are the strategy's effective knobs, resolved by the caller from
    the catalog. Execution and option settings are book columns (revisions
    0004/0005): sizing knobs are passed explicitly and ``option_settings`` is
    the book (a Mapping) supplying the option/leaps knobs.

    Sells go first — risk breaches in their own urgency order, then signalled
    exits — so their proceeds fund the same run's buys.

    Returns an empty list when nothing signals; callers must not manufacture a
    trade in that case.
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

    working = _WorkingState(
        cash=float(getattr(state, "cash", 0.0)),
        positions=dict(cast(Mapping[str, float], getattr(state, "positions", {}))),
        avg_cost=dict(cast(Mapping[str, float], getattr(state, "avg_cost", {}))),
    )
    selections: list[TradeSelection] = []

    for ticker in order_sell_candidates(sell_candidates, forced_sells, selection_seed):
        if len(selections) >= max_trades:
            break
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue
        qty = auto_trader_policy.closing_sell_qty(working.positions.get(ticker, 0.0))
        if qty <= 0:
            continue
        selections.append(("sell", ticker, qty, float(price), None, None))
        working.cash += (qty * float(price)) - fee
        working.positions.pop(ticker, None)
        working.avg_cost.pop(ticker, None)

    selections.extend(
        prepare_buy_trades(
            option_settings,
            instrument_mode,
            buy_candidates,
            prices,
            iv_rank_proxy,
            working,
            fee,
            max_buys=max_trades - len(selections),
            trade_size_pct=trade_size_pct,
            max_position_pct=max_position_pct,
            selection_seed=selection_seed,
        )
    )
    return selections


def _size_buy_for_ticker(
    option_settings: auto_trader_policy.AccountPolicyInput,
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
            option_settings,
            ticker,
            iv_rank_proxy,
        )
        if not ok:
            return None
        trade_price = float(
            auto_trader_policy.estimate_option_premium(
                price,
                delta_est,
                # Indexed directly: option_settings is an AccountPolicyInput
                # protocol (__getitem__ only), not a Mapping, so the row_* helpers
                # do not apply. row_int is exactly this coercion over a lookup.
                coerce_int(option_settings["option_min_dte"]),
                coerce_int(option_settings["option_max_dte"]),
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
        qty = auto_trader_policy.apply_leaps_buy_qty_limits(qty, trade_price, option_settings)
        if qty <= 0:
            return None

    return ticker, qty, trade_price, delta_est, iv_est


def prepare_buy_trades(
    option_settings: auto_trader_policy.AccountPolicyInput,
    instrument_mode: str,
    buy_candidates: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    state: TradePreparationStateLike,
    fee: float,
    *,
    max_buys: int,
    trade_size_pct: float | None,
    max_position_pct: float | None,
    selection_seed: str = "",
) -> list[TradeSelection]:
    """Size and fund up to *max_buys* of the signal-selected candidates.

    Candidates are reordered by *selection_seed* — see ``order_signal_candidates``.
    Sizing and funding are separate: each candidate is sized on its own against
    the book's policy, then ``allocate_buy_quantities`` splits the cash across
    them, the same allocation the backtest engine uses.
    """
    if max_buys <= 0:
        return []

    sized: list[tuple[str, float, int, float | None, float | None]] = []
    for ticker in auto_trader_policy.order_signal_candidates(buy_candidates, seed=selection_seed):
        if len(sized) >= max_buys:
            break
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue
        prepared = _size_buy_for_ticker(
            option_settings,
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
            _ticker, qty, trade_price, delta_est, iv_est = prepared
            sized.append((ticker, trade_price, qty, delta_est, iv_est))

    granted = auto_trader_policy.allocate_buy_quantities(
        [(ticker, price, qty) for ticker, price, qty, _d, _iv in sized],
        cash=float(state.cash),
        fee_per_trade=fee,
    )
    return [
        ("buy", ticker, granted[ticker], price, delta_est, iv_est)
        for ticker, price, _qty, delta_est, iv_est in sized
        if granted.get(ticker, 0) >= 1
    ]


def order_sell_candidates(
    sell_candidates: list[str],
    forced_sells: list[str],
    selection_seed: str = "",
) -> list[str]:
    """Risk breaches first in their own urgency order, then signalled exits.

    Signalled exits carry no ranking of their own, so they are ordered the way
    buys are rather than by position in the ticker file.
    """
    ordered = list(forced_sells)
    ordered.extend(
        ticker
        for ticker in auto_trader_policy.order_signal_candidates(sell_candidates, seed=selection_seed)
        if ticker not in forced_sells
    )
    return ordered


def prepare_sell_trade(
    sell_candidates: list[str],
    forced_sells: list[str],
    prices: dict[str, float],
    state: AccountStateLike,
    instrument_mode: str,
    selection_seed: str = "",
) -> tuple[str, int, float] | None:
    """Prepare the first sellable ticker, closing the position outright.

    A sell exits the whole position, matching ``execution_service._apply_sells``.
    """
    for ticker in order_sell_candidates(sell_candidates, forced_sells, selection_seed):
        price = prices.get(ticker)
        if price is None or price <= 0:
            continue

        qty = auto_trader_policy.closing_sell_qty(state.positions[ticker])
        if qty <= 0:
            continue

        return ticker, qty, float(price)
    return None
