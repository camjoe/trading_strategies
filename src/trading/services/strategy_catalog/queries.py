"""Read-side contracts for strategy catalog operator surfaces."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from trading.backtesting.domain.optimization.promotion_gate import (
    PromotionGateResult,
    evaluate_promotion_gate,
)
from trading.backtesting.optimizer_models import (
    CompoundedOOSSeries,
    ExperimentStatus,
    OptimizationExperimentRecord,
    OptimizationManifestRecord,
    OptimizationTrialRecord,
    OptimizationWindowRecord,
)
from trading.backtesting.repositories.optimization_repository import (
    fetch_experiment_by_id,
    fetch_manifest_for_experiment,
    fetch_recent_experiments,
    fetch_trials_for_experiment,
    fetch_windows_for_experiment,
)
from trading.backtesting.services.optimizer_aggregation_service import fetch_compounded_oos
from trading.domain.strategies.registry import PRIMITIVE_CATALOG
from trading.models.strategy.strategy_record import StrategyRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.strategies import StrategyRepository


def fetch_strategy_catalog(conn: sqlite3.Connection) -> list[StrategyRecord]:
    return StrategyRepository(conn).fetch_all()


def fetch_primitive_catalog() -> list[dict[str, object]]:
    return [
        {
            "primitive": spec.primitive,
            "style": spec.style,
            "description": spec.description,
            "default_params": dict(spec.knob_schema),
            "required_features": list(spec.required_features),
        }
        for spec in sorted(PRIMITIVE_CATALOG.values(), key=lambda item: item.primitive)
    ]


def _account_names(conn: sqlite3.Connection) -> dict[int, str]:
    return {account.id: account.name for account in AccountRepository(conn).fetch_all()}


def _account_name(conn: sqlite3.Connection, account_id: int) -> str:
    return _account_names(conn).get(account_id, f"account #{account_id}")


def fetch_optimization_history(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
) -> list[tuple[OptimizationExperimentRecord, str]]:
    account_names = _account_names(conn)
    return [
        (experiment, account_names.get(experiment.account_id, f"account #{experiment.account_id}"))
        for experiment in fetch_recent_experiments(conn, limit=limit)
    ]


@dataclass(frozen=True)
class OptimizationWindowDetail:
    """One walk-forward window and every candidate evaluated on its training interval."""

    window: OptimizationWindowRecord
    trials: list[OptimizationTrialRecord]


@dataclass(frozen=True)
class OptimizationDetail:
    """Everything persisted about one experiment, assembled for an operator surface.

    Mirrors what ``backtest-optimize-show`` prints, so the CLI and the Strategy Lab
    describe a run identically. ``gate`` is computed by the same function
    ``backtest-optimize-promote`` checks, so a preview can never disagree with what
    an actual promotion attempt would do.

    A failed experiment carries no windows, trials, compounded series, or manifest —
    it never got far enough to persist an audit tree.
    """

    experiment: OptimizationExperimentRecord
    account_name: str
    gate: PromotionGateResult
    windows: list[OptimizationWindowDetail]
    compounded_oos: CompoundedOOSSeries | None
    manifest: OptimizationManifestRecord | None


def _experiment_gate(experiment: OptimizationExperimentRecord) -> PromotionGateResult:
    return evaluate_promotion_gate(
        oos_mean_winner_return_pct=experiment.oos_mean_winner_return_pct,
        oos_mean_baseline_return_pct=experiment.oos_mean_baseline_return_pct,
        oos_windows_beat_baseline=experiment.oos_windows_beat_baseline,
        window_count=experiment.window_count,
        holdout_winner_return_pct=experiment.holdout_winner_return_pct,
        holdout_baseline_return_pct=experiment.holdout_baseline_return_pct,
    )


def fetch_optimization_detail(
    conn: sqlite3.Connection,
    *,
    experiment_id: int,
) -> OptimizationDetail | None:
    """Assemble one experiment's full audit record, or ``None`` if unknown.

    Trials are nested under the window they were evaluated on rather than returned
    flat, so the multiple-testing record reads in the order the search happened.
    """
    experiment = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    if experiment is None:
        return None

    account_name = _account_name(conn, experiment.account_id)
    gate = _experiment_gate(experiment)

    if experiment.status == ExperimentStatus.FAILED:
        return OptimizationDetail(
            experiment=experiment,
            account_name=account_name,
            gate=gate,
            windows=[],
            compounded_oos=None,
            manifest=None,
        )

    trials_by_window: dict[int, list[OptimizationTrialRecord]] = {}
    for trial in fetch_trials_for_experiment(conn, experiment_id=experiment_id):
        trials_by_window.setdefault(trial.window_id, []).append(trial)

    return OptimizationDetail(
        experiment=experiment,
        account_name=account_name,
        gate=gate,
        windows=[
            OptimizationWindowDetail(window=window, trials=trials_by_window.get(window.id, []))
            for window in fetch_windows_for_experiment(conn, experiment_id=experiment_id)
        ],
        compounded_oos=fetch_compounded_oos(conn, experiment_id=experiment_id),
        manifest=fetch_manifest_for_experiment(conn, experiment_id=experiment_id),
    )


def strategy_payload(record: StrategyRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "strategyKey": record.strategy_key,
        "primitive": record.primitive,
        "params": json.loads(record.params_json),
        "description": record.description,
        "status": record.status,
        "enabled": bool(record.enabled),
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }
