from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trading.services.accounts_service import create_account
from trading.domain import AccountAlreadyExistsError
from trading.models import AccountConfig, RotationConfig

from ..schemas import AdminCreateAccountRequest, AdminDeleteAccountRequest
from ..services import (
    fetch_account_row,
    build_account_summary,
    clean_text,
    db_conn,
    delete_account_and_dependents,
    update_account_rotation_settings,
    list_csv_exports,
    preview_csv_export,
)
from ..config import TEST_ACCOUNT_NAME

router = APIRouter()


def _build_create_account_kwargs(payload: AdminCreateAccountRequest) -> dict[str, object]:
    config = AccountConfig(
        descriptive_name=clean_text(payload.descriptiveName),
        goal_min_return_pct=payload.goalMinReturnPct,
        goal_max_return_pct=payload.goalMaxReturnPct,
        goal_period=payload.goalPeriod,
        learning_enabled=bool(payload.learningEnabled),
        risk_policy=payload.riskPolicy,
        stop_loss_pct=payload.stopLossPct,
        take_profit_pct=payload.takeProfitPct,
        trade_size_pct=payload.tradeSizePct,
        max_position_pct=payload.maxPositionPct,
        instrument_mode=payload.instrumentMode,
        option_strike_offset_pct=payload.optionStrikeOffsetPct,
        option_min_dte=payload.optionMinDte,
        option_max_dte=payload.optionMaxDte,
        option_type=clean_text(payload.optionType),
        target_delta_min=payload.targetDeltaMin,
        target_delta_max=payload.targetDeltaMax,
        max_premium_per_trade=payload.maxPremiumPerTrade,
        max_contracts_per_trade=payload.maxContractsPerTrade,
        iv_rank_min=payload.ivRankMin,
        iv_rank_max=payload.ivRankMax,
        roll_dte_threshold=payload.rollDteThreshold,
        profit_take_pct=payload.profitTakePct,
        max_loss_pct=payload.maxLossPct,
    )
    return dict(
        name=payload.name.strip(),
        strategy=payload.strategy.strip(),
        initial_cash=float(payload.initialCash),
        benchmark_ticker=payload.benchmarkTicker.strip().upper(),
        config=config,
    )


def _build_rotation_config(payload: AdminCreateAccountRequest) -> RotationConfig:
    profile: dict[str, object] = {
        "rotation_enabled": bool(payload.rotationEnabled),
        "rotation_mode": payload.rotationMode,
        "rotation_optimality_mode": payload.rotationOptimalityMode,
        "rotation_interval_days": payload.rotationIntervalDays,
        "rotation_interval_minutes": payload.rotationIntervalMinutes,
        "rotation_lookback_days": payload.rotationLookbackDays,
        "rotation_schedule": payload.rotationSchedule,
        "rotation_regime_strategy_risk_on": payload.rotationRegimeStrategyRiskOn,
        "rotation_regime_strategy_neutral": payload.rotationRegimeStrategyNeutral,
        "rotation_regime_strategy_risk_off": payload.rotationRegimeStrategyRiskOff,
        "rotation_overlay_mode": payload.rotationOverlayMode,
        "rotation_overlay_min_tickers": payload.rotationOverlayMinTickers,
        "rotation_overlay_confidence_threshold": payload.rotationOverlayConfidenceThreshold,
        "rotation_active_index": int(payload.rotationActiveIndex),
        "rotation_last_at": payload.rotationLastAt,
        "rotation_active_strategy": payload.rotationActiveStrategy,
    }
    if payload.rotationOverlayWatchlist is not None:
        profile["rotation_overlay_watchlist"] = payload.rotationOverlayWatchlist
    return RotationConfig.from_profile(profile)


@router.post("/api/admin/accounts/create")
def api_admin_create_account(payload: AdminCreateAccountRequest) -> dict[str, object]:
    with db_conn() as conn:
        try:
            create_account(conn, **_build_create_account_kwargs(payload))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except AccountAlreadyExistsError as error:
            raise HTTPException(status_code=400, detail=f"Account create failed: {error}") from error

        update_account_rotation_settings(conn, payload.name.strip(), _build_rotation_config(payload))

        account = fetch_account_row(conn, payload.name.strip())
        return {"status": "ok", "account": build_account_summary(conn, account)}


@router.post("/api/admin/accounts/delete")
def api_admin_delete_account(payload: AdminDeleteAccountRequest) -> dict[str, object]:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Deletion requires explicit confirmation.")

    if payload.accountName.strip() == TEST_ACCOUNT_NAME:
        raise HTTPException(status_code=400, detail="TEST Account is virtual and cannot be deleted.")

    counts = delete_account_and_dependents(payload.accountName.strip())
    return {"status": "ok", "deleted": counts}


@router.get("/api/admin/exports/csv")
def api_csv_exports() -> dict[str, object]:
    return list_csv_exports()


@router.get("/api/admin/exports/csv/preview")
def api_csv_export_preview(
    exportName: str = Query(..., min_length=1),
    fileName: str = Query(..., min_length=1),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    return preview_csv_export(exportName, fileName, limit)
