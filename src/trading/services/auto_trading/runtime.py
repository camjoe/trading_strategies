"""Runtime auto-trading orchestration and broker reconciliation."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from dataclasses import asdict

import pandas as pd

from common.coercion import row_expect_int
from common.time import parse_utc_iso
from common.time import utc_now_iso
from collections.abc import Callable, Mapping

from trading.models import AccountRecord
from trading.models.orders.broker_order import BrokerOrder, OrderFill
from trading.domain.broker_connection import BrokerConnection
from trading.domain.feature_provider import FeatureFetcherSet
from trading.domain.market_hours import is_regular_us_equity_market_open
from trading.services.accounts import get_account
from trading.services.accounting import record_trade
from trading.services.universe import resolve_named_universes
from trading.repositories.portfolio_risk_snapshots import PortfolioRiskSnapshotRepository
from trading.repositories.sleeve_risk_decisions import SleeveRiskDecisionRepository
from trading.repositories.accounts import AccountRepository
from trading.domain.rotation import (
    is_rotation_due,
)
from trading.services.auto_trading.execution import (
    FeatureHistoryFn,
    build_feature_history_fn,
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
    reconcile_open_orders_impl,
    resolve_reconciliation_exec_id,
)
from trading.services.auto_trading.runtime_rotation import rotate_runtime_account
from trading.services.market_data import MarketDataProvider
from trading.services.auto_trading.runtime_sleeve_risk import (
    persist_normalized_sleeve_risk_decisions,
    persist_sleeve_risk_snapshot,
)
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.services.sleeves.execution import generate_sleeve_trade_intents
from trading.services.sleeves.sector_config import load_symbol_sector_map
from trading.services.sleeves.rotation import (
    RotationPolicyConfig,
    evaluate_and_apply_sleeve_rotation,
)
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    build_sleeve_shadow_evaluation,
)
from trading.repositories.positions import PositionRepository
from trading.repositories.books import BookRepository
from trading.repositories.book_bridge import default_book_id, book_id_for_sleeve
from trading.models.execution.book_trade_intent import BookTradeIntent
from trading.services.execution.submission import submit_book_intents
from trading.services.execution.gate import AllowAllGate
from trading.services.execution.pre_submit_gate import BookPreSubmitGate
from trading.services.execution.nav import mark_account_to_market
from trading.services.execution.reconciliation import reconcile_book_equity

logger = logging.getLogger(__name__)

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
        update_account_rotation_state_fn=AccountRepository(conn).update_rotation_state,
        get_account_fn=get_account,
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
    _prices: dict[str, float],
    _snapshot_time: str,
) -> None:
    # The caller always supplies the broker and owns the disconnect lifecycle.
    broker = _injected_broker
    assert broker is not None, "_record_runtime_trade requires an injected broker"
    account_id = row_expect_int(account, "id")

    def _book_submit_record_trade(
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
        # Account mode is the account's single default book. Submit through the shared
        # execution service (writes the clean orders/fills/positions/ledger + book
        # balances) instead of the legacy broker_orders + record_trade path.
        book_id = default_book_id(conn, account_id)
        intent = BookTradeIntent(
            book_id=book_id,
            account_id=account_id,
            strategy_id=None,
            symbol=ticker,
            side=side,
            qty=float(qty),
            requested_price=float(price),
        )
        # Reconciliation ran once pre-flight (see run_for_account); the per-trade gate
        # keeps only the stale-price + notional-cap checks.
        gate = BookPreSubmitGate(prices=_prices, snapshot_time=_snapshot_time, reconcile=False)

        def _bridge_to_account_ledger(_intent: BookTradeIntent, _order_id: int, placed: BrokerOrder) -> None:
            # Keep the legacy account ledger (trades) in sync so account_report /
            # snapshots stay aligned with the book path until 2c fully retires it.
            record_trade(
                conn,
                account_name=account_name,
                side=side,
                ticker=ticker,
                qty=float(placed.filled_qty) if placed.filled_qty > 0 else float(qty),
                price=placed.avg_fill_price if placed.avg_fill_price is not None else price,
                fee=fee,
                trade_time=trade_time,
                note=note,
            )

        submit_book_intents(
            conn,
            book_id=book_id,
            account_id=account_id,
            intents=[intent],
            broker=broker,
            gate=gate,
            fee=fee,
            on_fill=_bridge_to_account_ledger,
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
        record_trade_fn=_book_submit_record_trade,
        trade_time_iso=trade_time_iso,
    )


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


def _persist_sleeve_risk_snapshot(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    kill_switch_triggered: bool,
    payload: dict[str, object],
) -> None:
    # Exposure is sourced from the clean book positions/equity (the submission path's
    # source of truth); the sleeve_positions/strategy_sleeves tables are frozen once
    # sleeve mode submits through the book path. `compute_current_exposure_snapshot`
    # only reads `.symbol`/`.market_value` and `.current_equity`, which book records carry.
    persist_sleeve_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        kill_switch_triggered=kill_switch_triggered,
        payload=payload,
        fetch_sleeve_positions_for_account_fn=lambda c, *, account_id: PositionRepository(c).fetch_for_account(
            account_id=account_id
        ),
        fetch_strategy_sleeves_for_account_fn=lambda c, *, account_id: BookRepository(c).fetch_for_account(
            account_id=account_id
        ),
        upsert_portfolio_risk_snapshot_fn=PortfolioRiskSnapshotRepository(conn).upsert,
        symbol_sector_map=load_symbol_sector_map(),
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
        insert_sleeve_risk_decision_fn=lambda c, **kwargs: SleeveRiskDecisionRepository(c).insert(**kwargs),
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
    config = RotationPolicyConfig(
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
            incumbent=sleeve_eval.incumbent,
            challengers=sleeve_eval.challengers,
            config=config,
            decision_time=decision_time,
        )


def _resolve_account_universe(account: AccountRecord, global_universe: list[str]) -> list[str]:
    """Return the account-specific universe, falling back to the global one."""
    raw = account.trade_universes
    if not raw:
        return global_universe
    names: object = json.loads(raw)
    if not isinstance(names, list) or not names:
        return global_universe
    return resolve_named_universes([str(n) for n in names])


def _sleeve_risk_decisions_from_gate(
    decisions: list[SleeveRiskDecision],
    sleeve_by_book: dict[int, SleeveTradeIntent],
) -> list[dict[str, object]]:
    """Convert the gate's book-bucketed decisions into sleeve-keyed audit dicts.

    Under book-as-bucket the gate emits decisions with ``sleeve_id`` set to the
    book id; translate back to the real sleeve id so the sleeve risk audit trail
    stays meaningful.
    """
    audit_rows: list[dict[str, object]] = []
    for decision in decisions:
        row = asdict(decision)
        book_id = row.get("sleeve_id")
        sleeve = sleeve_by_book.get(int(book_id)) if book_id is not None else None
        if sleeve is not None:
            row["sleeve_id"] = sleeve.sleeve_id
        audit_rows.append(row)
    return audit_rows


def _persist_sleeve_run_audit(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    risk_decisions: list[dict[str, object]],
    kill_switch_reasons: list[str],
    summary: dict[str, object],
) -> None:
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
            "summary": summary,
        },
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
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    histories: Mapping[str, pd.Series] | None = None,
    feature_history_fn: FeatureHistoryFn | None = None,
) -> int:
    account_id = row_expect_int(account, "id")
    snapshot_time = utc_now_iso()
    effective_universe = _resolve_account_universe(account, universe)
    _run_sleeve_rotation_decisions(conn, account=account, decision_time=snapshot_time)
    intents = generate_sleeve_trade_intents(
        conn,
        account=account,
        universe=effective_universe,
        prices=prices,
        iv_rank_proxy=iv_rank_proxy,
        min_trades=min_trades,
        max_trades=max_trades,
        fee=fee,
        histories=histories,
        feature_history_fn=feature_history_fn,
    )
    if not intents:
        _persist_sleeve_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=[],
            kill_switch_reasons=[],
            summary={"submitted_count": 0, "blocked_count": 0, "rescaled_count": 0, "allowed_count": 0},
        )
        return 0

    # Each sleeve is one book; map its intent to that bridging book and keep the
    # book → sleeve context for the audit trail and fill notes.
    book_intents: list[BookTradeIntent] = []
    sleeve_by_book: dict[int, SleeveTradeIntent] = {}
    for sleeve_intent in intents:
        book_id = book_id_for_sleeve(conn, sleeve_intent.sleeve_id, create=True)
        assert book_id is not None
        book_intents.append(
            BookTradeIntent(
                book_id=book_id,
                account_id=sleeve_intent.account_id,
                strategy_id=None,
                symbol=sleeve_intent.symbol,
                side=sleeve_intent.side,
                qty=float(sleeve_intent.qty),
                requested_price=float(sleeve_intent.requested_price),
            )
        )
        sleeve_by_book[book_id] = sleeve_intent

    # Pre-flight: NAV-mark books, then run the equity reconciliation kill switch once
    # for the run (consistent with account mode — reconciliation is per-run, not
    # per-book). The batch gate then applies the notional caps + stale-price across all
    # books with reconcile=False, so cross-book exposure caps are enforced together.
    mark_account_to_market(conn, account_id=account_id, prices=prices, as_of=snapshot_time)
    reconciliation_reasons = reconcile_book_equity(conn, account_id=account_id, now_iso=snapshot_time)
    gate = BookPreSubmitGate(
        prices=prices,
        snapshot_time=snapshot_time,
        reconcile=False,
        config=SleeveRiskGateConfig(symbol_sector_map=load_symbol_sector_map()),
    )
    gate_result = gate.evaluate(conn, account_id=account_id, intents=book_intents)

    risk_decisions = _sleeve_risk_decisions_from_gate(gate_result.decisions, sleeve_by_book)
    kill_switch_reasons = list(gate_result.kill_switch_reasons) + reconciliation_reasons
    for reason in kill_switch_reasons:
        risk_decisions.append({"action": "block", "reason_code": reason})
    allowed_count = sum(1 for d in gate_result.decisions if d.action == "allow")
    summary_counts: dict[str, object] = {
        "blocked_count": len(gate_result.blocked_intents),
        "rescaled_count": len(gate_result.rescaled_intents),
        "allowed_count": allowed_count,
    }

    # A kill switch (stale-price or reconciliation) holds the whole run.
    approved_intents = [] if kill_switch_reasons else gate_result.approved_intents
    if not approved_intents:
        _persist_sleeve_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=risk_decisions,
            kill_switch_reasons=kill_switch_reasons,
            summary={"submitted_count": 0, **summary_counts},
        )
        return 0

    approved_by_book: dict[int, list[BookTradeIntent]] = defaultdict(list)
    for book_intent in approved_intents:
        approved_by_book[book_intent.book_id].append(book_intent)

    broker = broker_factory(account)
    try:
        submitted_count = 0
        for book_id, book_intents_for_book in approved_by_book.items():
            sleeve = sleeve_by_book[book_id]

            def _bridge_to_account_ledger(
                intent: BookTradeIntent, _order_id: int, placed: BrokerOrder, _sleeve: SleeveTradeIntent = sleeve
            ) -> None:
                fill_price = (
                    float(placed.avg_fill_price)
                    if placed.avg_fill_price is not None
                    else float(intent.requested_price or 0.0)
                )
                fill_qty = float(placed.filled_qty) if placed.filled_qty > 0 else float(intent.qty)
                fill_time = placed.updated_at or utc_now_iso()
                record_trade(
                    conn,
                    account_name=account_name,
                    side=intent.side,
                    ticker=intent.symbol,
                    qty=fill_qty,
                    price=fill_price,
                    fee=float(fee),
                    trade_time=fill_time,
                    note=f"sleeve_fill sleeve_id={_sleeve.sleeve_id} strategy={_sleeve.strategy_name}",
                )

            result = submit_book_intents(
                conn,
                book_id=book_id,
                account_id=account_id,
                intents=book_intents_for_book,
                broker=broker,
                gate=AllowAllGate(),  # gating already ran once above for the whole batch
                fee=fee,
                on_fill=_bridge_to_account_ledger,
            )
            submitted_count += result.submitted_count
            if KILL_SWITCH_REASON_BROKER_API_ANOMALY in result.kill_switch_reasons:
                kill_switch_reasons.append(KILL_SWITCH_REASON_BROKER_API_ANOMALY)
                risk_decisions.append(
                    {
                        "action": "block",
                        "reason_code": KILL_SWITCH_REASON_BROKER_API_ANOMALY,
                        "sleeve_id": sleeve.sleeve_id,
                    }
                )
                break

        _persist_sleeve_run_audit(
            conn,
            account_id=account_id,
            snapshot_time=snapshot_time,
            risk_decisions=risk_decisions,
            kill_switch_reasons=kill_switch_reasons,
            summary={"submitted_count": submitted_count, **summary_counts},
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
    *,
    histories: Mapping[str, pd.Series] | None = None,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    provider: MarketDataProvider | None = None,
) -> int:
    now_iso = utc_now_iso()
    if not _is_runtime_submission_window_open(now_iso):
        return 0
    resolved_execution_mode = validate_execution_mode(execution_mode)
    feature_history_fn = build_feature_history_fn(feature_fetchers)
    if resolved_execution_mode == EXECUTION_MODE_SLEEVE:
        # Sleeve rotation is per-book (each sleeve's own champion/challenger inside
        # _run_sleeve_mode_for_account). The account-level rotation only maintained a
        # fallback strategy for unassigned sleeves, which are now simply not traded —
        # every book must carry its own assignment or it does not trade.
        account = get_account(conn, account_name)
        return _run_sleeve_mode_for_account(
            conn,
            account_name=account_name,
            account=account,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            min_trades=min_trades,
            max_trades=max_trades,
            fee=fee,
            broker_factory=broker_factory,
            feature_fetchers=feature_fetchers,
            histories=histories,
            feature_history_fn=feature_history_fn,
        )
    # Open one broker connection for the entire account trade loop so that
    # keepalive (e.g. IBKR Web API /tickle) remains effective across all
    # trades in the run.  Broker settings (broker_type, live_trading_enabled)
    # are stable within a single run — rotation updates strategy, not broker
    # config — so it is safe to resolve the broker from the initial account row.
    bootstrap_account = get_account(conn, account_name)
    effective_universe = _resolve_account_universe(bootstrap_account, universe)
    account_id = row_expect_int(bootstrap_account, "id")

    # Pre-flight (once per run): NAV-mark the account's books to market, then run the
    # equity reconciliation kill switch. It is a per-run check, not per-trade — after a
    # fill, book equity drifts from the snapshot by the fee, so the per-trade gate skips
    # it (reconcile=False). A mismatch holds the whole run.
    mark_account_to_market(conn, account_id=account_id, prices=prices, as_of=now_iso)
    reconciliation_reasons = reconcile_book_equity(conn, account_id=account_id, now_iso=now_iso)
    if reconciliation_reasons:
        logger.warning(
            "Account %s pre-submit reconciliation kill switch: %s; holding the run.",
            account_name,
            ", ".join(reconciliation_reasons),
        )
        return 0

    broker = broker_factory(bootstrap_account)
    try:
        return run_for_account_impl(
            conn,
            account_name,
            effective_universe,
            prices,
            iv_rank_proxy,
            min_trades,
            max_trades,
            fee,
            histories=histories,
            feature_history_fn=feature_history_fn,
            get_account_fn=get_account,
            utc_now_iso_fn=utc_now_iso,
            rotate_account_if_due_fn=lambda c, n, a, i: _rotate_runtime_account(c, n, a, i),
            record_prepared_trade_fn=lambda *args, **kwargs: _record_runtime_trade(
                *args, **kwargs, _injected_broker=broker, _prices=prices, _snapshot_time=now_iso
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
    *,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
) -> int:
    """Poll the account broker for fill updates on all open persisted clean orders.

    For each open ``orders`` row the broker reports fills on, this function:
      - Inserts any new ``order_fills`` rows and applies them to the book
        (positions/ledger/balances via the shared ``apply_book_fill``)
      - Updates the ``orders`` row status/fill state
      - Mirrors a completed fill into the legacy account ledger (``trades``)

    Returns the number of orders that were newly FILLED in this call.

    Called periodically for accounts with broker-managed open orders. It is a no-op
    for paper accounts, which fill synchronously and report no open trades.
    """
    return reconcile_open_orders_impl(
        conn,
        account_name,
        account,
        fee,
        get_broker_for_account_fn=broker_factory,
        record_trade_fn=record_trade,
    )


def reconcile_open_ib_orders(
    conn: sqlite3.Connection,
    account_name: str,
    account: AccountRecord,
    fee: float,
    *,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
) -> int:
    """Compatibility alias for the old broker reconciliation name."""
    return reconcile_open_broker_orders(conn, account_name, account, fee, broker_factory=broker_factory)
