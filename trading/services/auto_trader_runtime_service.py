from __future__ import annotations

import sqlite3
from typing import Callable, Mapping, cast

from common.time import utc_now_iso
from trading.models.broker_order import BrokerOrder, OrderStatus
from trading.brokers.factory import get_broker_for_account
from trading.services.accounts_service import get_account
from trading.domain.accounting import compute_account_state
from trading.services.accounting_service import load_trades, record_trade
from trading.repositories.broker_orders_repository import (
    fetch_open_broker_orders,
    insert_broker_order,
    insert_order_fill,
    update_broker_order_status,
)
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
from trading.backtesting.domain.strategy_signals import resolve_strategy
from trading.domain import auto_trader_policy
from trading.features.base import ExternalFeatureBundle
from trading.features.news_feature_provider import NewsFeatureProvider
from trading.features.policy_feature_provider import PolicyFeatureProvider
from trading.features.social_feature_provider import SocialFeatureProvider
from trading.repositories.rotation_repository import update_account_rotation_state
from trading.repositories.rotation_repository import (
    close_rotation_episode,
    fetch_closed_rotation_episodes,
    fetch_open_rotation_episode,
    insert_rotation_episode,
)
from trading.repositories.snapshots_repository import fetch_snapshot_count_between
from trading.domain.rotation import (
    is_rotation_due,
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_optimality_mode,
    resolve_rotation_mode,
)
from trading.services.auto_trader_service import (
    parse_runtime_as_of_iso as parse_runtime_as_of_iso_impl,
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
    RotationDeps,
)
from trading.services.rotation_service import (
    compute_live_account_metrics as compute_live_account_metrics_impl,
    fetch_rotation_overlay_tickers as fetch_rotation_overlay_tickers_impl,
    parse_as_of_iso as parse_as_of_iso_impl,
    rotate_account_if_due as rotate_account_if_due_impl,
    select_regime_strategy as select_regime_strategy_impl,
    select_optimal_strategy as select_optimal_strategy_impl,
    sync_rotation_episode as sync_rotation_episode_impl,
)
from trading.services.reporting_service import compute_market_value_and_unrealized, fetch_latest_prices
from trading.services.trade_execution_service import (
    build_leaps_candidates as build_leaps_candidates_impl,
    prepare_buy_trade as prepare_buy_trade_impl,
    prepare_sell_trade as prepare_sell_trade_impl,
    prepare_trade_selection as prepare_trade_selection_impl,
    record_prepared_trade as record_prepared_trade_impl,
    refresh_account_state as refresh_account_state_impl,
    run_for_account as run_for_account_impl,
)


_policy_rotation_provider: PolicyFeatureProvider | None = None
_news_rotation_provider: NewsFeatureProvider | None = None
_social_rotation_provider: SocialFeatureProvider | None = None


def _get_policy_rotation_provider() -> PolicyFeatureProvider:
    global _policy_rotation_provider
    if _policy_rotation_provider is None:
        _policy_rotation_provider = PolicyFeatureProvider()
    return _policy_rotation_provider


def _get_news_rotation_provider() -> NewsFeatureProvider:
    global _news_rotation_provider
    if _news_rotation_provider is None:
        _news_rotation_provider = NewsFeatureProvider()
    return _news_rotation_provider


def _get_social_rotation_provider() -> SocialFeatureProvider:
    global _social_rotation_provider
    if _social_rotation_provider is None:
        _social_rotation_provider = SocialFeatureProvider()
    return _social_rotation_provider


def _fetch_policy_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    try:
        return _get_policy_rotation_provider().get_features(ticker)
    except Exception:
        return ExternalFeatureBundle.unavailable(source="etf-proxies")


def _fetch_news_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    try:
        return _get_news_rotation_provider().get_features(ticker)
    except Exception:
        return ExternalFeatureBundle.unavailable(source="rss+vader")


def _fetch_social_rotation_bundle(ticker: str) -> ExternalFeatureBundle:
    try:
        return _get_social_rotation_provider().get_features(ticker)
    except Exception:
        return ExternalFeatureBundle.unavailable(source="reddit+gtrends")


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
        select_regime_strategy_impl_fn=select_regime_strategy_impl,
        parse_rotation_schedule_fn=parse_rotation_schedule,
        parse_as_of_iso_fn=_parse_runtime_as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns,
        fetch_policy_features_fn=_fetch_policy_rotation_bundle,
        fetch_news_features_fn=_fetch_news_rotation_bundle,
        fetch_social_features_fn=_fetch_social_rotation_bundle,
        fetch_rotation_overlay_tickers_fn=_fetch_runtime_rotation_overlay_tickers,
        resolve_rotation_mode_fn=cast(Callable[[sqlite3.Row], str], resolve_rotation_mode),
        resolve_active_strategy_fn=cast(Callable[[sqlite3.Row], str], resolve_active_strategy),
        resolve_optimality_mode_fn=cast(Callable[[sqlite3.Row], str], resolve_optimality_mode),
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes,
    )


def _fetch_runtime_rotation_overlay_tickers(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
) -> list[str]:
    return fetch_rotation_overlay_tickers_impl(
        conn,
        account,
        load_trades_fn=load_trades,
        compute_account_state_fn=compute_account_state,
    )


def _compute_runtime_live_account_metrics(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
) -> dict[str, float]:
    return compute_live_account_metrics_impl(
        conn,
        account,
        load_trades_fn=load_trades,
        compute_account_state_fn=compute_account_state,
        fetch_latest_prices_fn=fetch_latest_prices,
        compute_market_value_and_unrealized_fn=compute_market_value_and_unrealized,
    )


def _sync_runtime_rotation_episode(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    now_iso: str,
) -> None:
    if not hasattr(conn, "execute"):
        return
    sync_rotation_episode_impl(
        conn,
        account,
        now_iso,
        resolve_active_strategy_fn=cast(Callable[[sqlite3.Row], str], resolve_active_strategy),
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode,
        insert_rotation_episode_fn=insert_rotation_episode,
        close_rotation_episode_fn=close_rotation_episode,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between,
        compute_live_account_metrics_fn=_compute_runtime_live_account_metrics,
    )


def _rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
) -> sqlite3.Row:
    _sync_runtime_rotation_episode(conn, account, now_iso)
    deps = RotationDeps(
        rotate_account_if_due_impl_fn=rotate_account_if_due_impl,
        is_rotation_due_fn=lambda row: is_rotation_due(cast(Mapping[str, object], row), as_of_iso=now_iso),
        resolve_rotation_mode_fn=cast(Callable[[sqlite3.Row], str], resolve_rotation_mode),
        select_optimal_strategy_fn=_select_runtime_rotation_strategy,
        resolve_active_strategy_fn=cast(Callable[[sqlite3.Row], str], resolve_active_strategy),
        parse_rotation_schedule_fn=parse_rotation_schedule,
        next_rotation_state_fn=lambda row, as_of: next_rotation_state(cast(Mapping[str, object], row), as_of_iso=as_of),
        update_account_rotation_state_fn=update_account_rotation_state,
        get_account_fn=get_account,
    )
    rotated = rotate_runtime_account_if_due_impl(conn, account_name, account, now_iso, deps)
    _sync_runtime_rotation_episode(conn, rotated, now_iso)
    return rotated


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
):
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
        choose_buy_ticker_fn=cast(
            Callable[[list[str], dict[str, float], object, bool], str],
            auto_trader_policy.choose_buy_ticker,
        ),
    )


def _prepare_runtime_sell_trade(
    can_sell: list[str],
    forced_sell: str | None,
    prices: dict[str, float],
    state,
    learning_enabled: bool,
    instrument_mode: str,
):
    return prepare_sell_trade_impl(
        can_sell,
        forced_sell,
        prices,
        state,
        learning_enabled,
        instrument_mode,
        choose_sell_ticker_fn=cast(
            Callable[[list[str], dict[str, float], object, bool], str],
            auto_trader_policy.choose_sell_ticker,
        ),
        choose_sell_qty_fn=auto_trader_policy.choose_sell_qty,
    )


def _resolve_strategy_style(strategy_name: str | None) -> str | None:
    """Resolve a strategy name to its StrategySpec.strategy_style.

    Returns None if the name is absent or unrecognised so that choose_side
    falls back to SELL_BIAS_DEFAULT rather than raising.
    """
    if not strategy_name:
        return None
    try:
        return resolve_strategy(strategy_name).strategy_style
    except Exception:
        return None


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
        choose_side_fn=lambda forced_sell, can_sell, strategy_name: auto_trader_policy.choose_side(
            forced_sell, can_sell, _resolve_strategy_style(strategy_name)
        ),
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
    broker = get_broker_for_account(account)
    try:
        def _broker_aware_record_trade(
            conn: sqlite3.Connection,
            *,
            account_name: str,
            side: str,
            ticker: str,
            qty: float,
            price: float,
            fee: float,
            trade_time: str,
            note: str | None,
        ) -> None:
            order = BrokerOrder(
                account_id=int(account["id"]),
                ticker=ticker,
                side=side,
                qty=qty,
                price=price,
            )
            filled = broker.place_order(order)

            if filled.broker_order_id:
                insert_broker_order(conn, filled)
                for fill in filled.fills:
                    insert_order_fill(conn, filled.broker_order_id, fill)

            if filled.status == OrderStatus.FILLED:
                record_trade(
                    conn,
                    account_name=account_name,
                    side=side,
                    ticker=ticker,
                    qty=qty,
                    price=filled.avg_fill_price if filled.avg_fill_price is not None else price,
                    fee=fee,
                    trade_time=trade_time,
                    note=note,
                )

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
            record_trade_fn=_broker_aware_record_trade,
            utc_now_iso_fn=utc_now_iso,
            build_trade_note_fn=auto_trader_policy.build_trade_note,
        )
    finally:
        broker.disconnect()


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
        resolve_active_strategy_fn=cast(Callable[[sqlite3.Row], str], resolve_active_strategy),
        refresh_account_state_fn=_refresh_runtime_account_state,
        resolve_forced_sell_ticker_fn=auto_trader_policy.choose_sell_ticker_by_risk,
        prepare_trade_selection_fn=_prepare_runtime_trade_selection,
        record_prepared_trade_fn=_record_runtime_trade,
    )


def reconcile_open_ib_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    fee: float,
) -> int:
    """Poll the account broker for fill updates on all open persisted broker orders.

    For each order that has transitioned to FILLED since it was last persisted,
    this function:
      - Updates the ``broker_orders`` row to FILLED with avg fill price
      - Inserts any new ``order_fills`` rows
      - Calls ``record_trade`` so the fill is reflected in the account ledger

    Returns the number of orders that were newly FILLED in this call.

    This should be called periodically (e.g. once per trading loop iteration)
    for accounts with broker-managed open orders. It is a no-op for paper
    accounts since paper orders are synchronously filled and report no open
    trades through the broker interface.
    """
    broker = get_broker_for_account(account)

    open_rows = fetch_open_broker_orders(conn, account_id=int(account["id"]))
    if not open_rows:
        broker.disconnect()
        return 0

    open_ids = {row["broker_order_id"]: row for row in open_rows}
    try:
        live_orders = broker.get_open_trades()
        now = utc_now_iso()
        newly_filled = 0

        for live in live_orders:
            if live.broker_order_id not in open_ids:
                continue
            persisted = open_ids[live.broker_order_id]

            # Persist any new fills not yet in the DB.
            for fill in live.fills:
                insert_order_fill(conn, live.broker_order_id, fill)

            # Update the order row with latest status.
            update_broker_order_status(
                conn,
                broker_order_id=live.broker_order_id,
                status=live.status,
                filled_qty=live.filled_qty,
                avg_fill_price=live.avg_fill_price,
                commission=live.commission,
                updated_at=now,
            )

            if live.status == OrderStatus.FILLED:
                record_trade(
                    conn,
                    account_name=account_name,
                    side=persisted["side"],
                    ticker=persisted["ticker"],
                    qty=live.filled_qty,
                    price=live.avg_fill_price if live.avg_fill_price is not None else persisted["requested_price"],
                    fee=fee,
                    trade_time=now,
                    note=f"ib-fill order={live.broker_order_id}",
                )
                newly_filled += 1

        return newly_filled
    finally:
        broker.disconnect()
