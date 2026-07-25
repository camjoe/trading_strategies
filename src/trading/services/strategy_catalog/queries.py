"""Read-side contracts for strategy catalog operator surfaces."""

from __future__ import annotations

import json
import sqlite3

from trading.backtesting.optimizer_models import OptimizationExperimentRecord
from trading.backtesting.repositories.optimization_repository import fetch_recent_experiments
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


def fetch_optimization_history(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
) -> list[tuple[OptimizationExperimentRecord, str]]:
    account_names = {account.id: account.name for account in AccountRepository(conn).fetch_all()}
    return [
        (experiment, account_names.get(experiment.account_id, f"account #{experiment.account_id}"))
        for experiment in fetch_recent_experiments(conn, limit=limit)
    ]


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
