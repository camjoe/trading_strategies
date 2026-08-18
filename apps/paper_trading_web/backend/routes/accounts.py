from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from infrastructure.market_data.factory import build_provider
from trading.domain.exceptions import ValidationError
from trading.services.accounts.queries import list_account_snapshots
from trading.services.books.configuration import (
    BookConfigurationView,
    configure_book,
    fetch_account_book_configurations,
)
from trading.services.books.operations import fetch_book_operational_data
from trading.services.evaluation.queries import fetch_strategy_evaluation_for_account_row
from trading.services.execution.ledger.queries import list_account_trades

from ..account_contract import build_account_params_update_command
from ..account_options import get_account_config_options
from ..schemas import AccountParamsRequest, BookParamsRequest
from ..services.accounts.backtests import (
    fetch_latest_backtest_metrics,
    fetch_latest_backtest_summary,
)
from ..services.accounts.benchmark import (
    attach_live_benchmark_summary,
    build_live_benchmark_overlay,
)
from ..services.accounts.data_access import (
    build_snapshot_payload,
    build_trade_payload,
    fetch_visible_account_rows,
    require_account_row,
)
from ..services.accounts.mutations import update_account_params
from ..services.accounts.summaries import (
    build_account_list_payload,
    build_account_summary,
    build_account_summary_and_positions,
    build_comparison_account_payload,
)
from ..services.db import db_conn
from ..services.evaluation import build_evaluation_summary_payload
from ..services.shaping import camelize_keys

router = APIRouter()

# Request-field name → rotation policy field, for the book params write path.
# Must stay in step with ``ROTATION_POLICY_FIELDS``; a test asserts it does,
# because a knob that is added or dropped in the domain and missed here is
# silently un-editable rather than a visible error.
ROTATION_POLICY_REQUEST_NAMES = {
    "minTradesInWindow": "min_trades_in_window",
    "outperformanceThresholdBps": "outperformance_threshold_bps",
    "cooldownDays": "cooldown_days",
    "riskAdjustedReturnWeight": "risk_adjusted_return_weight",
    "stabilityWeight": "stability_weight",
    "drawdownPenaltyWeight": "drawdown_penalty_weight",
    "regimeFitWeight": "regime_fit_weight",
}


def _book_payload(view: BookConfigurationView) -> dict[str, object]:
    book = view.book
    policy = view.rotation_policy
    return {
        "name": book.name,
        "status": book.status,
        "isDefault": bool(book.is_default),
        "strategy": view.strategy,
        "startEquity": book.start_equity,
        "currentCash": book.current_cash,
        "currentEquity": book.current_equity,
        # The book's resolved tickers. Writes still take universe *names*
        # (`tradeUniverses` on the PATCH body); the server expands them.
        "tradeSymbols": json.loads(book.trade_symbols),
        "goalMinReturnPct": book.goal_min_return_pct,
        "goalMaxReturnPct": book.goal_max_return_pct,
        "goalPeriod": book.goal_period,
        "learningEnabled": bool(book.learning_enabled),
        "riskPolicy": book.risk_policy,
        "stopLossPct": book.stop_loss_pct,
        "takeProfitPct": book.take_profit_pct,
        "tradeSizePct": book.trade_size_pct,
        "maxPositionPct": book.max_position_pct,
        "maxTradesPerRun": book.max_trades_per_run,
        "instrumentMode": book.instrument_mode,
        "optionStrikeOffsetPct": book.option_strike_offset_pct,
        "optionMinDte": book.option_min_dte,
        "optionMaxDte": book.option_max_dte,
        "optionType": book.option_type,
        "targetDeltaMin": book.target_delta_min,
        "targetDeltaMax": book.target_delta_max,
        "maxPremiumPerTrade": book.max_premium_per_trade,
        "maxContractsPerTrade": book.max_contracts_per_trade,
        "ivRankMin": book.iv_rank_min,
        "ivRankMax": book.iv_rank_max,
        "rollDteThreshold": book.roll_dte_threshold,
        "optionProfitTakePct": book.option_profit_take_pct,
        "optionMaxLossPct": book.option_max_loss_pct,
        "rotation": {
            "enabled": view.rotation_enabled,
            "schedule": list(view.rotation_schedule),
            "lookbackDays": view.rotation_lookback_days,
        },
        "rotationPolicy": {
            "minTradesInWindow": policy.min_trades_in_window,
            "outperformanceThresholdBps": policy.outperformance_threshold_bps,
            "cooldownDays": policy.cooldown_days,
            "riskAdjustedReturnWeight": policy.risk_adjusted_return_weight,
            "stabilityWeight": policy.stability_weight,
            "drawdownPenaltyWeight": policy.drawdown_penalty_weight,
            "regimeFitWeight": policy.regime_fit_weight,
        },
    }


@router.get("/api/accounts/config/options")
def api_account_config_options() -> dict[str, object]:
    """Return ordered option values and defaults for the account configuration editor."""
    return get_account_config_options()


@router.get("/api/accounts")
def api_accounts() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        provider = build_provider()
        rows = fetch_visible_account_rows(conn)
        accounts = [build_account_list_payload(build_account_summary(conn, row, provider=provider)) for row in rows]
        accounts.sort(key=lambda item: str(item["name"]))
        return {"accounts": accounts}


@router.get("/api/accounts/compare")
def api_accounts_compare() -> dict[str, list[dict[str, object]]]:
    with db_conn() as conn:
        provider = build_provider()
        comparison: list[dict[str, object]] = []
        for row in fetch_visible_account_rows(conn):
            summary = build_account_summary(conn, row, provider=provider)
            snapshots = list_account_snapshots(conn, row.id, limit=100)
            attach_live_benchmark_summary(
                summary,
                build_live_benchmark_overlay(str(summary.get("benchmark") or ""), snapshots, provider=provider),
            )
            latest_backtest = fetch_latest_backtest_metrics(conn, row.name)
            evaluation = fetch_strategy_evaluation_for_account_row(conn, row)
            comparison.append(
                build_comparison_account_payload(
                    summary,
                    latest_backtest,
                    build_evaluation_summary_payload(evaluation),
                )
            )
        comparison.sort(key=lambda item: str(item["name"]))
        return {"accounts": comparison}


@router.get("/api/accounts/{account_name}")
def api_account_detail(account_name: str) -> dict[str, object]:
    with db_conn() as conn:
        provider = build_provider()
        account = require_account_row(conn, account_name)
        summary, positions = build_account_summary_and_positions(conn, account, provider=provider)

        snapshots = list_account_snapshots(conn, account.id, limit=100)
        overlay = build_live_benchmark_overlay(str(summary.get("benchmark") or ""), snapshots, provider=provider)
        attach_live_benchmark_summary(summary, overlay)
        trades = list_account_trades(conn, account.id)
        latest_backtest = fetch_latest_backtest_summary(conn, account.name)
        latest_backtest_metrics = fetch_latest_backtest_metrics(conn, account.name)
        book_views = fetch_account_book_configurations(conn, account_name=account_name)
        book_names = {view.book.id: view.book.name for view in book_views}
        operations = fetch_book_operational_data(conn, account_name=account_name)

        return {
            "account": summary,
            "books": [_book_payload(view) for view in book_views],
            "positions": positions,
            "latestBacktest": latest_backtest,
            "latestBacktestMetrics": latest_backtest_metrics,
            "liveBenchmarkOverlay": camelize_keys(overlay),
            "snapshots": [build_snapshot_payload(snapshot) for snapshot in snapshots],
            "trades": [build_trade_payload(trade, book_names=book_names) for trade in trades[-100:]],
            "bookPositions": [
                {
                    "bookId": row["book_id"],
                    "bookName": row["book_name"],
                    "ticker": row["ticker"],
                    "qty": row["qty"],
                    "avgCost": row["avg_cost"],
                    "marketPrice": (
                        float(row["market_value"]) / float(row["qty"]) if float(row["qty"]) != 0.0 else 0.0
                    ),
                    "marketValue": row["market_value"],
                    "unrealizedPnl": row["unrealized_pnl"],
                }
                for row in operations["positions"]
            ],
            "bookSnapshots": [
                {
                    "bookId": row["book_id"],
                    "bookName": row["book_name"],
                    **build_snapshot_payload(row["snapshot"]),
                }
                for row in operations["snapshots"]
            ],
            "bookMetrics": [
                {
                    "bookId": row["book_id"],
                    "bookName": row["book_name"],
                    "metricDate": row["metric"].metric_date,
                    "returnPct": row["metric"].return_pct,
                    "drawdownPct": row["metric"].drawdown_pct,
                    "hitRate": row["metric"].hit_rate,
                    "riskAdjustedScore": row["metric"].risk_adjusted_score,
                    "tradeCount": row["metric"].trade_count,
                    "feesTotal": row["metric"].fees_total,
                }
                for row in operations["metrics"]
            ],
            "riskDecisions": [
                {
                    "bookId": row["book_id"],
                    "bookName": row["book_name"],
                    "decisionTime": row["decision"].decision_time,
                    "symbol": row["decision"].symbol,
                    "side": row["decision"].side,
                    "action": row["decision"].action,
                    "reason": row["decision"].reason_code,
                    "requestedNotional": row["decision"].requested_notional,
                    "approvedNotional": row["decision"].approved_notional,
                }
                for row in operations["risk_decisions"]
            ],
        }


@router.patch("/api/accounts/{account_name}/params")
def api_update_account_params(account_name: str, body: AccountParamsRequest) -> dict[str, str]:
    """Partially update mutable account parameters.

    All fields are optional — omitted fields are left unchanged.

    Returns ``{"status": "ok"}`` on success.  Raises ``HTTPException`` if the
    account does not exist.
    """
    with db_conn() as conn:
        require_account_row(conn, account_name)
        command = build_account_params_update_command(body)
        try:
            update_account_params(
                conn,
                account_name,
                command=command,
            )
        except ValidationError as exc:
            # Bad parameter values are a semantic validation failure on this PATCH
            # (422) — a route-specific status choice, so it stays a direct mapping
            # here rather than the app-level 400. An unexpected ValueError surfaces
            # as 500. See docs/adr/007-ui-error-mapping.md.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}


@router.patch("/api/accounts/{account_name}/books/{book_name}/params")
def api_update_book_params(
    account_name: str,
    book_name: str,
    body: BookParamsRequest,
) -> dict[str, str]:
    """Partially update one book's execution, universe, and rotation settings.

    All fields are optional — omitted fields are left unchanged. Rotation
    scheduling and rotation policy are separate groups on the same request.
    """
    with db_conn() as conn:
        command = build_account_params_update_command(body)
        raw_policy = body.rotationPolicy.model_dump(exclude_none=True) if body.rotationPolicy else {}
        policy_names = ROTATION_POLICY_REQUEST_NAMES
        scheduling_names = {
            "enabled": "rotation_enabled",
            "schedule": "rotation_schedule",
            "lookback_days": "rotation_lookback_days",
        }
        try:
            configure_book(
                conn,
                account_name=account_name,
                book_name=book_name,
                strategy=command.strategy,
                config=command.config,
                rotation_scheduling={
                    scheduling_names[name]: value for name, value in command.rotation_settings.items()
                },
                rotation_policy={policy_names[name]: value for name, value in raw_policy.items()},
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok"}
