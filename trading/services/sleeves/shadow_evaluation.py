from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from common.coercion import row_expect_int
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns
from trading.domain.rotation import parse_rotation_schedule
from trading.domain.sleeve_rotation import SleeveStrategyMetrics
from trading.models import AccountRecord
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_active_strategy_param_set,
    fetch_strategy_sleeves_for_account,
)
from trading.services.sleeves.helpers import mean as _sleeve_mean
from trading.services.sleeves.helpers import resolve_window_bounds as _resolve_window_bounds_shared

# Default historical lookback window for challenger shadow evaluation.
DEFAULT_SHADOW_ROLLING_WINDOW_DAYS = 30


@dataclass(frozen=True, slots=True)
class SleeveShadowEvaluation:
    sleeve_id: int
    incumbent_strategy: str
    challengers: list[SleeveStrategyMetrics]


@dataclass(frozen=True, slots=True)
class ShadowEvaluationRun:
    account_id: int
    account_name: str
    window_start_day: str
    window_end_day: str
    sleeves: list[SleeveShadowEvaluation]


def _mean(values: list[float]) -> float:
    return _sleeve_mean(values)


def _resolve_strategy_schedule(account: AccountRecord) -> list[str]:
    try:
        schedule = parse_rotation_schedule(account.rotation_schedule)
    except ValueError:
        schedule = []
    if not schedule:
        base_strategy = str(account.strategy).strip()
        return [base_strategy] if base_strategy else []
    return [name for name in schedule if name]


def _resolve_window_bounds(
    *,
    as_of_iso: str,
    rolling_window_days: int,
) -> tuple[str, str]:
    return _resolve_window_bounds_shared(as_of_iso=as_of_iso, rolling_window_days=rolling_window_days)


def build_challenger_metrics_from_backtest_returns(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    start_day: str,
    end_day: str,
) -> SleeveStrategyMetrics:
    rows = fetch_strategy_backtest_returns(
        conn,
        account_id=account_id,
        strategy_names=[strategy_name],
        start_day=start_day,
        end_day=end_day,
    )
    returns = [float(return_pct) for candidate, return_pct in rows if str(candidate).strip() == strategy_name]
    trade_count = len(returns)
    risk_adjusted_return = _mean(returns)
    stability = float(sum(1 for value in returns if value > 0.0)) / float(trade_count) if trade_count > 0 else 0.0
    drawdown_penalty = abs(min(returns)) if returns and min(returns) < 0 else 0.0
    param_set_row = fetch_active_strategy_param_set(conn, strategy_name=strategy_name)
    param_set_id = int(param_set_row["id"]) if param_set_row is not None and param_set_row["id"] is not None else None
    return SleeveStrategyMetrics(
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        trade_count=trade_count,
        risk_adjusted_return=risk_adjusted_return,
        stability=stability,
        drawdown_penalty=drawdown_penalty,
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
    account_id = row_expect_int(account, "id")
    schedule = _resolve_strategy_schedule(account)
    window_start_day, window_end_day = _resolve_window_bounds(
        as_of_iso=as_of_iso,
        rolling_window_days=rolling_window_days,
    )
    sleeve_rows = fetch_strategy_sleeves_for_account(conn, account_id=account_id)
    sleeves: list[SleeveShadowEvaluation] = []
    for sleeve_row in sleeve_rows:
        if str(sleeve_row["status"]).strip().lower() != "active":
            continue
        sleeve_id = int(sleeve_row["id"])
        assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
        if assignment is None:
            continue
        incumbent_strategy = str(assignment["strategy_name"]).strip()
        challengers: list[SleeveStrategyMetrics] = []
        for strategy_name in schedule:
            if strategy_name == incumbent_strategy:
                continue
            challengers.append(
                build_challenger_metrics_from_backtest_returns(
                    conn,
                    account_id=account_id,
                    strategy_name=strategy_name,
                    start_day=window_start_day,
                    end_day=window_end_day,
                )
            )
        sleeves.append(
            SleeveShadowEvaluation(
                sleeve_id=sleeve_id,
                incumbent_strategy=incumbent_strategy,
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
