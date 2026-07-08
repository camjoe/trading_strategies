from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from trading.domain.rotation import parse_rotation_schedule
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.models import AccountRecord
from trading.repositories.sleeves import SleeveRepository
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared
from trading.services.sleeves.rotation_metrics import build_rotation_strategy_metrics

DEFAULT_SHADOW_ROLLING_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class SleeveShadowEvaluation:
    sleeve_id: int
    incumbent_strategy: str
    incumbent: RotationStrategyMetrics
    challengers: list[RotationStrategyMetrics]


@dataclass(frozen=True, slots=True)
class ShadowEvaluationRun:
    account_id: int
    account_name: str
    window_start_day: str
    window_end_day: str
    sleeves: list[SleeveShadowEvaluation]


def _resolve_strategy_schedule(account: AccountRecord) -> list[str]:
    try:
        schedule = parse_rotation_schedule(account.rotation_schedule)
    except ValueError:
        schedule = []
    if not schedule:
        base_strategy = str(account.strategy).strip()
        return [base_strategy] if base_strategy else []
    return [name for name in schedule if name]


def _resolve_window_bounds(*, as_of_iso: str, rolling_window_days: int) -> tuple[str, str]:
    return _resolve_window_bounds_shared(as_of_iso=as_of_iso, rolling_window_days=rolling_window_days)


def build_sleeve_shadow_evaluation(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    as_of_iso: str,
    rolling_window_days: int = DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
) -> ShadowEvaluationRun:
    account_id = account.id
    schedule = _resolve_strategy_schedule(account)
    window_start_day, window_end_day = _resolve_window_bounds(
        as_of_iso=as_of_iso,
        rolling_window_days=rolling_window_days,
    )
    sleeve_repo = SleeveRepository(conn)
    param_set_repo = StrategyParamSetRepository(conn)
    all_sleeves = sleeve_repo.fetch_for_account(account_id=account_id)
    sleeves: list[SleeveShadowEvaluation] = []
    for sleeve in all_sleeves:
        if sleeve.status.strip().lower() != "active":
            continue
        assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve.id)
        if assignment is None:
            continue
        incumbent_strategy = assignment.strategy_name.strip()
        incumbent = build_rotation_strategy_metrics(
            conn,
            account=account,
            strategy_name=incumbent_strategy,
            param_set_id=assignment.param_set_id,
        )
        challengers: list[RotationStrategyMetrics] = []
        for strategy_name in schedule:
            if strategy_name == incumbent_strategy:
                continue
            active_param_set = param_set_repo.fetch_active(strategy_name=strategy_name)
            challengers.append(
                build_rotation_strategy_metrics(
                    conn,
                    account=account,
                    strategy_name=strategy_name,
                    param_set_id=active_param_set.id if active_param_set is not None else None,
                )
            )
        sleeves.append(
            SleeveShadowEvaluation(
                sleeve_id=sleeve.id,
                incumbent_strategy=incumbent_strategy,
                incumbent=incumbent,
                challengers=challengers,
            )
        )

    return ShadowEvaluationRun(
        account_id=account_id,
        account_name=str(account.name),
        window_start_day=window_start_day,
        window_end_day=window_end_day,
        sleeves=sleeves,
    )
