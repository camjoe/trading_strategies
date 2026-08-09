"""Read-side contracts for strategy catalog operator surfaces."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from backtesting.models.optimizer import (
    CompoundedOOSSeries,
    ExperimentWindowAudit,
    OptimizationExperimentRecord,
    OptimizationManifestRecord,
)
from backtesting.services.audit_service import (
    fetch_experiment_audit,
    fetch_recent_experiments,
)
from trading.domain.promotion_gate import (
    PromotionGateResult,
    evaluate_promotion_gate,
)
from trading.domain.strategies.registry import PRIMITIVE_CATALOG
from trading.models.strategy import StrategyRecord
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
    windows: list[ExperimentWindowAudit]
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
    """Assemble one experiment's operator view, or ``None`` if unknown.

    The audit tree comes from backtesting; this adds what only the catalog side
    knows — the owning account's name, and the promotion gate verdict.
    """
    audit = fetch_experiment_audit(conn, experiment_id=experiment_id)
    if audit is None:
        return None

    return OptimizationDetail(
        experiment=audit.experiment,
        account_name=_account_name(conn, audit.experiment.account_id),
        gate=_experiment_gate(audit.experiment),
        windows=audit.windows,
        compounded_oos=audit.compounded_oos,
        manifest=audit.manifest,
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
