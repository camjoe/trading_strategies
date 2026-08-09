from __future__ import annotations

import json
from functools import partial

from fastapi import APIRouter, HTTPException, Query

from backtesting.composition import run_backtest, run_backtest_metrics_only
from backtesting.models.optimizer import (
    CompoundedOOSSeries,
    ExperimentWindowAudit,
    OptimizationExperimentRecord,
    OptimizationManifestRecord,
    OptimizationTrialRecord,
    OptimizerConfig,
)
from backtesting.services.walk_forward_optimizer_service import run_and_persist_optimization
from infrastructure.market_data.factory import build_provider, resolve_provider_name
from trading.domain.exceptions import NotFoundError
from trading.services.strategy_catalog.mutations import (
    configure_strategy,
    create_strategy_variant,
    freeze_strategy,
)
from trading.services.strategy_catalog.optimizer_promotion import promote_optimization_experiment
from trading.services.strategy_catalog.queries import (
    fetch_optimization_detail,
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


def _trial_payload(trial: OptimizationTrialRecord) -> dict[str, object]:
    return {
        "candidateIndex": trial.candidate_index,
        "params": json.loads(trial.params_json),
        "paramsHash": trial.params_hash,
        "objectiveValue": trial.objective_value,
        "annualizedReturnPct": trial.annualized_return_pct,
        "maxDrawdownPct": trial.max_drawdown_pct,
        "tradeCount": trial.trade_count,
        "eligible": trial.eligible,
        "rejectionReason": trial.rejection_reason,
        "selected": trial.selected,
    }


def _window_payload(detail: ExperimentWindowAudit) -> dict[str, object]:
    return {
        "windowIndex": detail.window.window_index,
        "trainStart": detail.window.train_start,
        "trainEnd": detail.window.train_end,
        "testStart": detail.window.test_start,
        "testEnd": detail.window.test_end,
        "oosRunId": detail.window.oos_run_id,
        "trials": [_trial_payload(trial) for trial in detail.trials],
    }


def _compounded_payload(series: CompoundedOOSSeries | None) -> dict[str, object] | None:
    if series is None:
        return None
    return {
        "compoundedReturnPct": series.compounded_return_pct,
        "hasGaps": series.has_gaps,
        "points": [
            {
                "windowIndex": point.window_index,
                "testStart": point.test_start,
                "testEnd": point.test_end,
                "periodReturnPct": point.period_return_pct,
                "cumulativeReturnPct": point.cumulative_return_pct,
                "gapBefore": point.gap_before,
            }
            for point in series.points
        ],
    }


def _manifest_payload(manifest: OptimizationManifestRecord | None) -> dict[str, object] | None:
    if manifest is None:
        return None
    return {
        "manifestVersion": manifest.manifest_version,
        "bookId": manifest.book_id,
        "initialCash": manifest.initial_cash,
        "benchmarkTicker": manifest.benchmark_ticker,
        "slippageBps": manifest.slippage_bps,
        "feePerTrade": manifest.fee_per_trade,
        "effectiveExecution": json.loads(manifest.effective_execution_json),
        "tickersFile": manifest.tickers_file,
        "universeHistoryDir": manifest.universe_history_dir,
        "universeTickers": json.loads(manifest.universe_tickers_json),
        "universeSize": manifest.universe_size,
        "marketDataProvider": manifest.market_data_provider,
        "dataAsOf": manifest.data_as_of,
        "engineRevision": manifest.engine_revision,
        "createdAt": manifest.created_at,
    }


@router.get("/api/strategy-lab/optimizations/{experiment_id}")
def api_optimization_detail(experiment_id: int) -> dict[str, object]:
    """Show one optimization run's full audit record and promotion-gate preview."""
    with db_conn() as conn:
        detail = fetch_optimization_detail(conn, experiment_id=experiment_id)
        if detail is None:
            raise NotFoundError(f"Optimization experiment not found: {experiment_id}")
        experiment = detail.experiment
        return {
            "experiment": {
                **_experiment_payload(experiment, detail.account_name),
                "status": str(experiment.status),
                "failureStage": None if experiment.failure_stage is None else str(experiment.failure_stage),
                "failureMessage": experiment.failure_message,
                "startDate": experiment.start_date,
                "endDate": experiment.end_date,
                "trainMonths": experiment.train_months,
                "testMonths": experiment.test_months,
                "stepMonths": experiment.step_months,
                "holdoutMonths": experiment.holdout_months,
                "warmupMonths": experiment.warmup_months,
                "candidateBudget": experiment.candidate_budget,
                "holdoutRunId": experiment.holdout_run_id,
            },
            "gate": {"passed": detail.gate.passed, "reasons": list(detail.gate.reasons)},
            "windows": [_window_payload(window) for window in detail.windows],
            "compoundedOos": _compounded_payload(detail.compounded_oos),
            "manifest": _manifest_payload(detail.manifest),
        }


@router.post("/api/strategy-lab/optimizations")
def api_run_optimization(payload: RunOptimizationRequest) -> dict[str, object]:
    with db_conn() as conn:
        provider = build_provider()
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
                # One provider for the whole sweep: its cumulative call guard is
                # per instance, and a sweep runs a backtest per candidate per window.
                run_metrics_only_fn=partial(run_backtest_metrics_only, provider=provider),
                run_persisted_fn=partial(run_backtest, provider=provider),
                market_data_provider=resolve_provider_name(),
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
