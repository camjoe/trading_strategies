from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from trading.domain.evaluation_decision_score import derive_decision_score
from trading.domain.rotation import parse_rotation_schedule
from trading.models.sleeves.sleeve_strategy_metrics import SleeveStrategyMetrics
from trading.models import AccountRecord
from trading.repositories.sleeves import SleeveRepository
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.evaluation import fetch_strategy_evaluation_for_account_row
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared

DEFAULT_SHADOW_ROLLING_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class SleeveShadowEvaluation:
    sleeve_id: int
    incumbent_strategy: str
    incumbent: SleeveStrategyMetrics
    challengers: list[SleeveStrategyMetrics]


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


def build_sleeve_metrics_from_evaluation(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    strategy_name: str,
    param_set_id: int | None,
) -> SleeveStrategyMetrics:
    """Build sleeve rotation metrics from the canonical evaluation artifact.

    Both the incumbent and each challenger are scored through the same source —
    the strategy evaluation artifact's decision score — so champion/challenger
    comparison is apples-to-apples. The multi-component ``SleeveStrategyMetrics``
    collapses onto the single blended decision score for now; the richer
    component decomposition is deferred to the rotation-paradigm unification (2b).
    """
    artifact = fetch_strategy_evaluation_for_account_row(conn, account, strategy_name=strategy_name)
    decision = derive_decision_score(artifact)
    comparable_score = decision.score if decision.score is not None else 0.0
    return SleeveStrategyMetrics(
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        trade_count=artifact.backtest.trade_count or 0,
        risk_adjusted_return=comparable_score,
        stability=0.0,
        drawdown_penalty=0.0,
        cost_penalty=0.0,
        regime_fit=0.0,
    )


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
        incumbent = build_sleeve_metrics_from_evaluation(
            conn,
            account=account,
            strategy_name=incumbent_strategy,
            param_set_id=assignment.param_set_id,
        )
        challengers: list[SleeveStrategyMetrics] = []
        for strategy_name in schedule:
            if strategy_name == incumbent_strategy:
                continue
            active_param_set = param_set_repo.fetch_active(strategy_name=strategy_name)
            challengers.append(
                build_sleeve_metrics_from_evaluation(
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
