"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

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
from trading.repositories.sleeve_risk_decisions import insert_sleeve_risk_decision
from trading.repositories.sleeve_orders import (
    attach_sleeve_order_broker_order_id,
    fetch_sleeve_order_by_broker_order_id,
    insert_sleeve_order,
    update_sleeve_order_status,
)
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
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
from trading.services.auto_trading.inputs import (
    EXECUTION_MODE_ACCOUNT,
    EXECUTION_MODE_SLEEVE,
    validate_execution_mode,
)
from trading.services.auto_trading.runtime_reconciliation import (
    reconcile_open_broker_orders_impl,
    resolve_reconciliation_exec_id,
)
from trading.services.auto_trading.runtime_rotation import rotate_runtime_account
from trading.services.auto_trading.runtime_sleeve_risk import (
    compute_current_exposure_snapshot,
    is_snapshot_time_stale,
    persist_normalized_sleeve_risk_decisions,
    persist_sleeve_risk_snapshot,
)
from trading.services.sleeves.accounting import apply_sleeve_fill
from trading.services.sleeves.execution import SleeveTradeIntent, generate_sleeve_trade_intents
from trading.services.sleeves.risk_gate import (
    evaluate_sleeve_risk_gate,
)
from trading.services.sleeves.rotation import (
    SleeveRotationConfig,
    evaluate_and_apply_sleeve_rotation,
)
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    build_sleeve_shadow_evaluation,
)
from trading.services.sleeves.reconciliation import reconcile_sleeves_vs_latest_snapshot
from trading.repositories.sleeve_positions import fetch_sleeve_positions_for_account
from trading.repositories.sleeves import fetch_strategy_sleeves_for_account

# Kill-switch reason when required price marks are unavailable or invalid.
KILL_SWITCH_REASON_STALE_PRICE_DATA = "stale_price_data"
# Kill-switch reason when sleeve/account equity reconciliation is out of tolerance.
KILL_SWITCH_REASON_RECONCILIATION_MISMATCH = "reconciliation_mismatch"
# Kill-switch reason when no account snapshot exists for reconciliation guard.
KILL_SWITCH_REASON_RECONCILIATION_SNAPSHOT_MISSING = "reconciliation_snapshot_missing"
# Kill-switch reason when latest account snapshot is older than freshness threshold.
KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT = "stale_reconciliation_snapshot"
# Kill-switch reason when broker submission raises an exception.
KILL_SWITCH_REASON_BROKER_API_ANOMALY = "broker_api_anomaly"

# Maximum allowed age for account snapshot freshness validation (seconds).
MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS = 6 * 60 * 60


def _rotate_runtime_account(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    now_iso: str,
) -> AccountRecord:
    return rotate_runtime_account(
        conn,
        account_name,
        account,
        now_iso,
        is_rotation_due_fn=is_rotation_due,
        update_account_rotation_state_fn=update_account_rotation_state,
        get_account_fn=get_account,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes,
        fetch_open_rotation_episode_fn=fetch_open_rotation_episode,
        insert_rotation_episode_fn=insert_rotation_episode,
        close_rotation_episode_fn=close_rotation_episode,
        fetch_snapshot_count_between_fn=fetch_snapshot_count_between,
    )


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
    return resolve_reconciliation_exec_id(
        broker_order_id=broker_order_id,
        fill=fill,
        fill_index=fill_index,
    )


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
    return compute_current_exposure_snapshot(
        conn,
        account_id=account_id,
        fetch_sleeve_positions_for_account_fn=fetch_sleeve_positions_for_account,
        fetch_strategy_sleeves_for_account_fn=fetch_strategy_sleeves_for_account,
    )


def _persist_sleeve_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
) -> None:
    persist_sleeve_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        kill_switch_triggered=kill_switch_triggered,
        payload=payload,
        fetch_sleeve_positions_for_account_fn=fetch_sleeve_positions_for_account,
        fetch_strategy_sleeves_for_account_fn=fetch_strategy_sleeves_for_account,
        upsert_portfolio_risk_snapshot_fn=upsert_portfolio_risk_snapshot,
    )


def _persist_normalized_sleeve_risk_decisions(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    decision_time: str,
    risk_decisions: list[dict[str, object]],
) -> None:
    persist_normalized_sleeve_risk_decisions(
        conn,
        account_id=account_id,
        decision_time=decision_time,
        risk_decisions=risk_decisions,
        insert_sleeve_risk_decision_fn=insert_sleeve_risk_decision,
    )


def _is_snapshot_time_stale(
    *,
    snapshot_time: str | None,
    now_iso: str,
    max_age_seconds: int,
) -> bool:
    return is_snapshot_time_stale(
        snapshot_time=snapshot_time,
        now_iso=now_iso,
        max_age_seconds=max_age_seconds,
    )


def _run_sleeve_rotation_decisions(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    decision_time: str,
) -> None:
    rolling_window_days = (
        int(account.rotation_lookback_days)
        if account.rotation_lookback_days is not None and int(account.rotation_lookback_days) > 0
        else DEFAULT_SHADOW_ROLLING_WINDOW_DAYS
    )
    config = SleeveRotationConfig(
        rolling_window_days=rolling_window_days,
        config_version=f"sleeve-rotation:{decision_time[:10]}",
    )
    shadow_eval = build_sleeve_shadow_evaluation(
        conn,
        account=account,
        as_of_iso=decision_time,
        rolling_window_days=rolling_window_days,
    )
    for sleeve_eval in shadow_eval.sleeves:
        evaluate_and_apply_sleeve_rotation(
            conn,
            sleeve_id=sleeve_eval.sleeve_id,
            challengers=sleeve_eval.challengers,
            config=config,
            decision_time=decision_time,
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
    _run_sleeve_rotation_decisions(
        conn,
        account=account,
        decision_time=snapshot_time,
    )
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
        _persist_normalized_sleeve_risk_decisions(
            conn,
            account_id=account_id,
            decision_time=snapshot_time,
            risk_decisions=[],
        )
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
        if _is_snapshot_time_stale(
            snapshot_time=reconciliation.snapshot_time,
            now_iso=snapshot_time,
            max_age_seconds=MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
        ):
            kill_switch_reasons.append(KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT)
            approved_intents = []
            risk_decisions.append(
                {
                    "action": "block",
                    "reason_code": KILL_SWITCH_REASON_STALE_RECONCILIATION_SNAPSHOT,
                    "snapshot_time": reconciliation.snapshot_time,
                    "max_age_seconds": MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS,
                }
            )
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
        _persist_normalized_sleeve_risk_decisions(
            conn,
            account_id=account_id,
            decision_time=snapshot_time,
            risk_decisions=risk_decisions,
        )
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
        _persist_normalized_sleeve_risk_decisions(
            conn,
            account_id=account_id,
            decision_time=snapshot_time,
            risk_decisions=risk_decisions,
        )
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
    return reconcile_open_broker_orders_impl(
        conn,
        account_name,
        account,
        fee,
        get_broker_for_account_fn=get_broker_for_account,
        fetch_open_broker_orders_fn=fetch_open_broker_orders,
        fetch_sleeve_order_by_broker_order_id_fn=fetch_sleeve_order_by_broker_order_id,
        insert_order_fill_fn=insert_order_fill,
        update_broker_order_status_fn=update_broker_order_status,
        update_sleeve_order_status_fn=update_sleeve_order_status,
        record_trade_fn=record_trade,
    )


def reconcile_open_ib_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
) -> int:
    """Compatibility alias for the old broker reconciliation name."""
    return reconcile_open_broker_orders(conn, account_name, account, fee)
