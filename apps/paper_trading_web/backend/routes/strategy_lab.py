from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from trading.backtesting.backtest import run_backtest, run_backtest_metrics_only
from trading.backtesting.optimizer_models import OptimizationExperimentRecord, OptimizerConfig
from trading.backtesting.services.walk_forward_optimizer_service import run_and_persist_optimization
from trading.domain.exceptions import NotFoundError
from trading.services.strategy_catalog.mutations import (
    configure_strategy,
    create_strategy_variant,
    freeze_strategy,
)
from trading.services.strategy_catalog.optimizer_promotion import promote_optimization_experiment
from trading.services.strategy_catalog.queries import (
    fetch_optimization_history,
    fetch_primitive_catalog,
    fetch_strategy_catalog,
    strategy_payload,
)

from ..schemas import (
    ConfigureStrategyRequest,
    CreateStrategyVariantRequest,
    PromoteOptimizationRequest,
    RunOptimizationRequest,
)
from ..services.db import db_conn

router = APIRouter()


@router.get("/api/strategy-lab/catalog")
def api_strategy_catalog() -> dict[str, object]:
    with db_conn() as conn:
        return {
            "strategies": [strategy_payload(record) for record in fetch_strategy_catalog(conn)],
            "primitives": fetch_primitive_catalog(),
        }


@router.post("/api/strategy-lab/catalog")
def api_create_strategy(payload: CreateStrategyVariantRequest) -> dict[str, object]:
    with db_conn() as conn:
        try:
            record = create_strategy_variant(
                conn,
                strategy_key=payload.strategyKey,
                primitive=payload.primitive,
                params=payload.params,
                description=payload.description,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "ok", "strategy": strategy_payload(record)}


@router.patch("/api/strategy-lab/catalog/{strategy_key}")
def api_configure_strategy(strategy_key: str, payload: ConfigureStrategyRequest) -> dict[str, object]:
    """Edit a draft strategy variant's knobs and enabled flag (frozen variants reject edits)."""
    with db_conn() as conn:
        try:
            record = configure_strategy(
                conn,
                strategy_key=strategy_key,
                params=payload.params,
                enabled=payload.enabled,
            )
        except NotFoundError:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "ok", "strategy": strategy_payload(record)}


@router.post("/api/strategy-lab/catalog/{strategy_key}/freeze")
def api_freeze_strategy(strategy_key: str) -> dict[str, object]:
    """Freeze a draft strategy variant so its knobs become immutable and it is tradeable."""
    with db_conn() as conn:
        return {"status": "ok", "strategy": strategy_payload(freeze_strategy(conn, strategy_key=strategy_key))}


def _experiment_payload(experiment: OptimizationExperimentRecord, account_name: str) -> dict[str, object]:
    return {
        "id": experiment.id,
        "accountName": account_name,
        "primitive": experiment.primitive,
        "objectiveName": experiment.objective_name,
        "searchSpace": json.loads(experiment.search_space_json),
        "winnerParams": json.loads(experiment.winner_params_json),
        "windowCount": experiment.window_count,
        "oosMeanWinnerReturnPct": experiment.oos_mean_winner_return_pct,
        "oosMeanBaselineReturnPct": experiment.oos_mean_baseline_return_pct,
        "oosWindowsBeatBaseline": experiment.oos_windows_beat_baseline,
        "holdoutWinnerReturnPct": experiment.holdout_winner_return_pct,
        "holdoutBaselineReturnPct": experiment.holdout_baseline_return_pct,
        "promotedStrategyId": experiment.promoted_strategy_id,
        "createdAt": experiment.created_at,
    }


@router.get("/api/strategy-lab/optimizations")
def api_optimizations(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    with db_conn() as conn:
        return {
            "experiments": [
                _experiment_payload(experiment, account_name)
                for experiment, account_name in fetch_optimization_history(conn, limit=limit)
            ]
        }


@router.post("/api/strategy-lab/optimizations")
def api_run_optimization(payload: RunOptimizationRequest) -> dict[str, object]:
    with db_conn() as conn:
        try:
            summary = run_and_persist_optimization(
                conn,
                OptimizerConfig(
                    account_name=payload.account.strip(),
                    tickers_file=payload.tickersFile,
                    universe_history_dir=payload.universeHistoryDir,
                    strategy=payload.strategy.strip(),
                    search_space=payload.searchSpace,
                    start=payload.start,
                    end=payload.end,
                    lookback_months=payload.lookbackMonths,
                    slippage_bps=payload.slippageBps,
                    fee_per_trade=payload.fee,
                    allow_approximate_leaps=payload.allowApproximateLeaps,
                    train_months=payload.trainMonths,
                    test_months=payload.testMonths,
                    step_months=payload.stepMonths,
                    holdout_months=payload.holdoutMonths,
                    candidate_budget=payload.candidateBudget,
                    warmup_months=payload.warmupMonths,
                ),
                run_metrics_only_fn=run_backtest_metrics_only,
                run_persisted_fn=run_backtest,
            )
        except NotFoundError:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "ok", "experimentId": summary.experiment_id}


@router.post("/api/strategy-lab/optimizations/{experiment_id}/promote")
def api_promote_optimization(
    experiment_id: int,
    payload: PromoteOptimizationRequest,
) -> dict[str, object]:
    """Promote an optimization run's winner into a new strategy variant, optionally frozen."""
    with db_conn() as conn:
        try:
            record = promote_optimization_experiment(
                conn,
                experiment_id=experiment_id,
                new_strategy_key=payload.strategyKey,
                freeze=payload.freeze,
            )
        except NotFoundError:
            raise
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"status": "ok", "strategy": strategy_payload(record)}
