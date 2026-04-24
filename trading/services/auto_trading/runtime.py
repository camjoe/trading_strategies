"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_int
from common.time import parse_utc_iso
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.broker_order import BrokerOrder, OrderStatus
from trading.brokers.base import BrokerConnection
from trading.brokers.factory import get_broker_for_account
from trading.services.market_data.market_hours import is_regular_us_equity_market_open
from trading.services.accounts import get_account
from trading.domain.accounting import compute_account_state
from trading.services.accounting import list_account_trades, record_trade
from trading.repositories.broker_orders import (
    fetch_open_broker_orders,
    insert_broker_order,
    insert_order_fill,
    update_broker_order_status,
)
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
from trading.domain import auto_trader_policy
from trading.features.base import ExternalFeatureBundle
from trading.features.news_feature_provider import NewsFeatureProvider
from trading.features.policy_feature_provider import PolicyFeatureProvider
from trading.features.social_feature_provider import SocialFeatureProvider
from trading.repositories.rotation import update_account_rotation_state
from trading.repositories.rotation import (
    close_rotation_episode,
    fetch_closed_rotation_episodes,
    fetch_open_rotation_episode,
    insert_rotation_episode,
)
from trading.repositories.snapshots import fetch_snapshot_count_between
from trading.domain.rotation import (
    is_rotation_due,
    resolve_active_strategy,
)
from trading.services.auto_trading.execution import (
    prepare_trade_selection as prepare_trade_selection_impl,
    record_prepared_trade as record_prepared_trade_impl,
    refresh_account_state as refresh_account_state_impl,
    run_for_account as run_for_account_impl,
)
from trading.services.auto_trading.rotation import (
    compute_live_account_metrics as compute_live_account_metrics_impl,
    fetch_rotation_overlay_tickers as fetch_rotation_overlay_tickers_impl,
    sync_rotation_episode as sync_rotation_episode_impl,
)
from trading.services.auto_trading.rotation_bridge import (
    rotate_runtime_account_if_due as rotate_runtime_account_if_due_impl,
    select_account_rotation_strategy as select_account_rotation_strategy_impl,
    RotationDeps,
)
from trading.services.reporting import compute_market_value_and_unrealized, fetch_latest_prices
from trading.services.runtime_throttle import enforce_runtime_trade_throttles

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



def _select_runtime_rotation_strategy(
    conn: sqlite3.Connection,
    account: AccountRecord,
    as_of_iso: str,
) -> str | None:
    return select_account_rotation_strategy_impl(
        conn,
        account,
        as_of_iso,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns,
        fetch_policy_features_fn=_fetch_policy_rotation_bundle,
        fetch_news_features_fn=_fetch_news_rotation_bundle,
        fetch_social_features_fn=_fetch_social_rotation_bundle,
        fetch_rotation_overlay_tickers_fn=_fetch_runtime_rotation_overlay_tickers,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes,
    )


def _fetch_runtime_rotation_overlay_tickers(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> list[str]:
    return fetch_rotation_overlay_tickers_impl(
        conn,
        account,
        load_trades_fn=list_account_trades,
        compute_account_state_fn=compute_account_state,
    )


def _compute_runtime_live_account_metrics(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> dict[str, float]:
    return compute_live_account_metrics_impl(
        conn,
        account,
        load_trades_fn=list_account_trades,
        compute_account_state_fn=compute_account_state,
        fetch_latest_prices_fn=fetch_latest_prices,
        compute_market_value_and_unrealized_fn=compute_market_value_and_unrealized,
    )


def _sync_runtime_rotation_episode(
    conn: sqlite3.Connection,
    account: AccountRecord,
    now_iso: str,
) -> None:
    if not hasattr(conn, "execute"):
        return
    sync_rotation_episode_impl(
        conn,
        account,
        now_iso,
        resolve_active_strategy_fn=resolve_active_strategy,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode,
        insert_rotation_episode_fn=insert_rotation_episode,
        close_rotation_episode_fn=close_rotation_episode,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between,
        compute_live_account_metrics_fn=_compute_runtime_live_account_metrics,
    )


def _rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
) -> AccountRecord:
    _sync_runtime_rotation_episode(conn, account, now_iso)
    deps = RotationDeps(
        is_rotation_due_fn=lambda row: is_rotation_due(row, as_of_iso=now_iso),
        select_optimal_strategy_fn=_select_runtime_rotation_strategy,
        update_account_rotation_state_fn=update_account_rotation_state,
        get_account_fn=get_account,
    )
    rotated = rotate_runtime_account_if_due_impl(conn, account_name, account, now_iso, deps)
    _sync_runtime_rotation_episode(conn, rotated, now_iso)
    return rotated


def _refresh_runtime_account_state(conn: sqlite3.Connection, account: AccountRecord):
    return refresh_account_state_impl(conn, account)


def _record_runtime_trade(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    learning_enabled: bool,
    risk_policy: str,
    instrument_mode: str,
    active_strategy: str | None,
    fee: float,
    selection,
    forced_sell: str | None,
    trade_time_iso: str | None = None,
    *,
    _injected_broker: BrokerConnection | None = None,
) -> None:
    # When a broker is injected by the caller (e.g. run_for_account) we reuse
    # that shared connection and let the caller own the disconnect lifecycle.
    # When called standalone the function creates and disconnects its own broker.
    _owns_broker = _injected_broker is None
    broker = _injected_broker if _injected_broker is not None else get_broker_for_account(account)
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
                account_id=row_expect_int(account, "id"),
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
            trade_time_iso=trade_time_iso,
        )
    finally:
        if _owns_broker:
            broker.disconnect()


def _is_runtime_submission_window_open(now_iso: str) -> bool:
    return is_regular_us_equity_market_open(parse_utc_iso(now_iso))


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
    now_iso = utc_now_iso()
    if not _is_runtime_submission_window_open(now_iso):
        return 0
    # Open one broker connection for the entire account trade loop so that
    # keepalive (e.g. IBKR Web API /tickle) remains effective across all
    # trades in the run.  Broker settings (broker_type, live_trading_enabled)
    # are stable within a single run — rotation updates strategy, not broker
    # config — so it is safe to resolve the broker from the initial account row.
    bootstrap_account = get_account(conn, account_name)
    broker = get_broker_for_account(bootstrap_account)
    try:
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
            prepare_trade_selection_fn=prepare_trade_selection_impl,
            record_prepared_trade_fn=lambda *args, **kwargs: _record_runtime_trade(
                *args, **kwargs, _injected_broker=broker
            ),
            enforce_runtime_trade_throttles_fn=enforce_runtime_trade_throttles,
            is_submission_window_open_fn=_is_runtime_submission_window_open,
        )
    finally:
        broker.disconnect()


def reconcile_open_broker_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
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

    open_rows = fetch_open_broker_orders(conn, account_id=row_expect_int(account, "id"))
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


def reconcile_open_ib_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
) -> int:
    """Compatibility alias for the old broker reconciliation name."""
    return reconcile_open_broker_orders(conn, account_name, account, fee)
