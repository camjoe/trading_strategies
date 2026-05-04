"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from common.coercion import row_expect_int
from common.time import parse_utc_iso
from common.time import utc_now_iso
from trading.models import AccountRecord
from trading.models.broker_order import BrokerOrder, OrderFill, OrderStatus
from trading.brokers.base import BrokerConnection
from trading.brokers.factory import get_broker_for_account
from trading.services.market_data.market_hours import is_regular_us_equity_market_open
from trading.services.accounts import get_account
from trading.services.accounting import record_trade
from trading.repositories.broker_orders import (
    fetch_open_broker_orders,
    insert_broker_order,
    insert_order_fill,
    update_broker_order_status,
)
from trading.repositories.portfolio_risk_snapshots import upsert_portfolio_risk_snapshot
from trading.repositories.sleeve_orders import (
    attach_sleeve_order_broker_order_id,
    fetch_sleeve_order_by_broker_order_id,
    insert_sleeve_order,
    update_sleeve_order_status,
)
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
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
)
from trading.services.auto_trading.execution import (
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
from trading.services.auto_trading.inputs import (
    EXECUTION_MODE_ACCOUNT,
    EXECUTION_MODE_SLEEVE,
    validate_execution_mode,
)
from trading.services.sleeves.accounting import apply_sleeve_fill
from trading.services.sleeves.execution import SleeveTradeIntent, generate_sleeve_trade_intents
from trading.services.sleeves.risk_gate import (
    DEFAULT_SYMBOL_SECTOR_MAP,
    evaluate_sleeve_risk_gate,
    resolve_sector_for_symbol,
)
from trading.services.sleeves.reconciliation import reconcile_sleeves_vs_latest_snapshot
from trading.repositories.sleeve_positions import fetch_sleeve_positions_for_account
from trading.repositories.sleeves import fetch_strategy_sleeves_for_account

_policy_rotation_provider: PolicyFeatureProvider | None = None
_news_rotation_provider: NewsFeatureProvider | None = None
_social_rotation_provider: SocialFeatureProvider | None = None

# Kill-switch reason when required price marks are unavailable or invalid.
KILL_SWITCH_REASON_STALE_PRICE_DATA = "stale_price_data"
# Kill-switch reason when sleeve/account equity reconciliation is out of tolerance.
KILL_SWITCH_REASON_RECONCILIATION_MISMATCH = "reconciliation_mismatch"
# Kill-switch reason when no account snapshot exists for reconciliation guard.
KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING = "reconciliation_snapshot_missing"
# Kill-switch reason when broker submission raises an exception.
KILL_SWITCH_REASON_BROKER_API_ANOMALY = "broker_api_anomaly"


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
    return fetch_rotation_overlay_tickers_impl(conn, account)


def _compute_runtime_live_account_metrics(
    conn: sqlite3.Connection,
    account: AccountRecord,
) -> dict[str, float]:
    return compute_live_account_metrics_impl(conn, account)


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


def _resolve_reconciliation_exec_id(
    *,
    broker_order_id: str,
    fill: OrderFill,
    fill_index: int,
) -> str:
    if fill.exec_id:
        return fill.exec_id
    # Deterministic fallback for broker payloads that omit execution IDs.
    return f"{broker_order_id}:{fill.fill_time}:{fill.filled_qty}:{fill.fill_price}:{fill_index}"


def _insert_submitted_sleeve_order(
    conn: sqlite3.Connection,
    *,
    intent: SleeveTradeIntent,
    now_iso: str,
) -> int:
    return insert_sleeve_order(
        conn,
        account_id=intent.account_id,
        sleeve_id=intent.sleeve_id,
        strategy_name=intent.strategy_name,
        param_set_id=intent.param_set_id,
        rotation_decision_id=None,
        broker_order_id=None,
        symbol=intent.symbol,
        side=intent.side,
        qty=float(intent.qty),
        order_type="market",
        time_in_force="day",
        requested_price=float(intent.requested_price),
        status=OrderStatus.SUBMITTED.value,
        config_version=None,
        submitted_at=now_iso,
        updated_at=now_iso,
    )


def _compute_current_exposure_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> tuple[float, float, float, float]:
    position_rows = fetch_sleeve_positions_for_account(conn, account_id=account_id)
    gross_exposure = 0.0
    net_exposure = 0.0
    symbol_exposure: dict[str, float] = {}
    sector_exposure: dict[str, float] = {}
    for row in position_rows:
        symbol = str(row["symbol"]).upper().strip()
        market_value = float(row["market_value"])
        abs_value = abs(market_value)
        gross_exposure += abs_value
        net_exposure += market_value
        symbol_exposure[symbol] = symbol_exposure.get(symbol, 0.0) + abs_value
        sector = resolve_sector_for_symbol(symbol, symbol_sector_map=DEFAULT_SYMBOL_SECTOR_MAP)
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + abs_value

    sleeve_rows = fetch_strategy_sleeves_for_account(conn, account_id=account_id)
    total_equity = sum(float(row["current_equity"]) for row in sleeve_rows)
    max_symbol_concentration_pct = 0.0
    max_sector_concentration_pct = 0.0
    if total_equity > 0 and symbol_exposure:
        max_symbol_concentration_pct = max(symbol_exposure.values()) / total_equity
    if total_equity > 0 and sector_exposure:
        max_sector_concentration_pct = max(sector_exposure.values()) / total_equity
    return gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct


def _persist_sleeve_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
) -> None:
    gross_exposure, net_exposure, max_symbol_concentration_pct, max_sector_concentration_pct = _compute_current_exposure_snapshot(
        conn,
        account_id=account_id,
    )
    upsert_portfolio_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        max_symbol_concentration_pct=max_symbol_concentration_pct,
        max_sector_concentration_pct=max_sector_concentration_pct,
        drawdown_pct=None,
        leverage_proxy=None,
        daily_loss_pct=None,
        kill_switch_triggered=1 if kill_switch_triggered else 0,
        risk_payload_json=json.dumps(payload, sort_keys=True),
    )


def _run_sleeve_mode_for_account(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    account: AccountRecord,
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
) -> int:
    account_id = row_expect_int(account, "id")
    snapshot_time = utc_now_iso()
    intents = generate_sleeve_trade_intents(
        conn,
        account=account,
        universe=universe,
        prices=prices,
        iv_rank_proxy=iv_rank_proxy,
        min_trades=min_trades,
        max_trades=max_trades,
        fee=fee,
    )
    if not intents:
        _persist_sleeve_risk_snapshot(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            kill_switch_triggered=False,
            payload={
                "kill_switch_reasons": [],
                "risk_decisions": [],
                "summary": {"submitted_count": 0, "blocked_count": 0, "rescaled_count": 0, "allowed_count": 0},
            },
        )
        return 0
    gated = evaluate_sleeve_risk_gate(
        conn,
        account_id=account_id,
        intents=intents,
    )
    approved_intents = gated.approved_intents
    kill_switch_reasons: list[str] = []
    risk_decisions = [asdict(decision) for decision in gated.decisions]
    if approved_intents:
        stale_symbols = sorted(
            {
                intent.symbol
                for intent in approved_intents
                if prices.get(intent.symbol) is None or float(prices[intent.symbol]) <= 0
            }
        )
        if stale_symbols:
            kill_switch_reasons.append(KILL_SWITCH_REASON_STALE_PRICE_DATA)
            approved_intents = []
            risk_decisions.append(
                {
                    "action": "block",
                    "reason_code": KILL_SWITCH_REASON_STALE_PRICE_DATA,
                    "stale_symbols": stale_symbols,
                }
            )
    try:
        reconciliation = reconcile_sleeves_vs_latest_snapshot(conn, account_id=account_id)
        if not reconciliation.within_tolerance:
            kill_switch_reasons.append(KILL_SWITCH_REASON_RECONCILIATION_MISMATCH)
            approved_intents = []
            risk_decisions.append(
                {
                    "action": "block",
                    "reason_code": KILL_SWITCH_REASON_RECONCILIATION_MISMATCH,
                    "equity_difference": reconciliation.equity_difference,
                    "tolerance": reconciliation.tolerance,
                }
            )
    except ValueError:
        kill_switch_reasons.append(KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING)
        approved_intents = []
        risk_decisions.append(
            {
                "action": "block",
                "reason_code": KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING,
            }
        )

    if not approved_intents:
        _persist_sleeve_risk_snapshot(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            kill_switch_triggered=bool(kill_switch_reasons),
            payload={
                "kill_switch_reasons": kill_switch_reasons,
                "risk_decisions": risk_decisions,
                "summary": {
                    "submitted_count": 0,
                    "blocked_count": gated.blocked_count,
                    "rescaled_count": gated.rescaled_count,
                    "allowed_count": gated.allowed_count,
                },
            },
        )
        return 0

    broker = get_broker_for_account(account)
    try:
        submitted_count = 0
        for intent in approved_intents:
            submitted_at = utc_now_iso()
            sleeve_order_id = _insert_submitted_sleeve_order(
                conn,
                intent=intent,
                now_iso=submitted_at,
            )
            order = BrokerOrder(
                account_id=intent.account_id,
                ticker=intent.symbol,
                side=intent.side,
                qty=float(intent.qty),
                price=float(intent.requested_price),
            )
            try:
                broker_order = broker.place_order(order)
            except Exception as exc:
                kill_switch_reasons.append(KILL_SWITCH_REASON_BROKER_API_ANOMALY)
                risk_decisions.append(
                    {
                        "action": "block",
                        "reason_code": KILL_SWITCH_REASON_BROKER_API_ANOMALY,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "error": str(exc),
                    }
                )
                update_sleeve_order_status(
                    conn,
                    sleeve_order_id=sleeve_order_id,
                    status=OrderStatus.REJECTED.value,
                    updated_at=utc_now_iso(),
                )
                break
            updated_at = utc_now_iso()

            if broker_order.broker_order_id:
                if broker_order.submitted_at is None:
                    broker_order.submitted_at = submitted_at
                if broker_order.updated_at is None:
                    broker_order.updated_at = updated_at
                attach_sleeve_order_broker_order_id(
                    conn,
                    sleeve_order_id=sleeve_order_id,
                    broker_order_id=broker_order.broker_order_id,
                    updated_at=updated_at,
                )
                insert_broker_order(conn, broker_order)
                for fill in broker_order.fills:
                    insert_order_fill(conn, broker_order.broker_order_id, fill)

            update_sleeve_order_status(
                conn,
                sleeve_order_id=sleeve_order_id,
                status=broker_order.status.value,
                updated_at=updated_at,
            )

            if broker_order.status == OrderStatus.FILLED:
                fill_price = (
                    float(broker_order.avg_fill_price)
                    if broker_order.avg_fill_price is not None
                    else float(intent.requested_price)
                )
                fill_qty = float(broker_order.filled_qty) if broker_order.filled_qty > 0 else float(intent.qty)
                fill_time = broker_order.updated_at or updated_at
                apply_sleeve_fill(
                    conn,
                    sleeve_order_id=sleeve_order_id,
                    broker_fill_id=broker_order.broker_order_id,
                    exec_id=None,
                    filled_qty=fill_qty,
                    fill_price=fill_price,
                    commission=float(broker_order.commission),
                    fill_time=fill_time,
                    updated_at=updated_at,
                )
                record_trade(
                    conn,
                    account_name=account_name,
                    side=intent.side,
                    ticker=intent.symbol,
                    qty=fill_qty,
                    price=fill_price,
                    fee=float(fee),
                    trade_time=fill_time,
                    note=f"sleeve_fill sleeve_id={intent.sleeve_id} strategy={intent.strategy_name}",
                )
            submitted_count += 1
        _persist_sleeve_risk_snapshot(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            kill_switch_triggered=bool(kill_switch_reasons),
            payload={
                "kill_switch_reasons": kill_switch_reasons,
                "risk_decisions": risk_decisions,
                "summary": {
                    "submitted_count": submitted_count,
                    "blocked_count": gated.blocked_count,
                    "rescaled_count": gated.rescaled_count,
                    "allowed_count": gated.allowed_count,
                    "gross_exposure_before": gated.gross_exposure_before,
                    "gross_exposure_after": gated.gross_exposure_after,
                },
            },
        )
        return submitted_count
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
    execution_mode: str = EXECUTION_MODE_ACCOUNT,
) -> int:
    now_iso = utc_now_iso()
    if not _is_runtime_submission_window_open(now_iso):
        return 0
    resolved_execution_mode = validate_execution_mode(execution_mode)
    if resolved_execution_mode == EXECUTION_MODE_SLEEVE:
        account = get_account(conn, account_name)
        rotated_account = _rotate_runtime_account(conn, account_name, account, now_iso)
        return _run_sleeve_mode_for_account(
            conn,
            account_name=account_name,
            account=rotated_account,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            min_trades=min_trades,
            max_trades=max_trades,
            fee=fee,
        )
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
            record_prepared_trade_fn=lambda *args, **kwargs: _record_runtime_trade(
                *args, **kwargs, _injected_broker=broker
            ),
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
    account_id = row_expect_int(account, "id")
    try:
        live_orders = broker.get_open_trades()
        now = utc_now_iso()
        newly_filled = 0

        for live in live_orders:
            if live.broker_order_id not in open_ids:
                continue
            persisted = open_ids[live.broker_order_id]
            sleeve_order_row = fetch_sleeve_order_by_broker_order_id(
                conn,
                account_id=account_id,
                broker_order_id=live.broker_order_id,
            )

            # Persist any new fills not yet in the DB.
            for fill_index, fill in enumerate(live.fills):
                insert_order_fill(conn, live.broker_order_id, fill)
                if sleeve_order_row is not None:
                    apply_sleeve_fill(
                        conn,
                        sleeve_order_id=int(sleeve_order_row["id"]),
                        broker_fill_id=live.broker_order_id,
                        exec_id=_resolve_reconciliation_exec_id(
                            broker_order_id=live.broker_order_id,
                            fill=fill,
                            fill_index=fill_index,
                        ),
                        filled_qty=fill.filled_qty,
                        fill_price=fill.fill_price,
                        commission=fill.commission,
                        fill_time=fill.fill_time,
                        updated_at=now,
                    )

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
            if sleeve_order_row is not None:
                update_sleeve_order_status(
                    conn,
                    sleeve_order_id=int(sleeve_order_row["id"]),
                    status=live.status.value,
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
