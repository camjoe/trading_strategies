from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# backtest_runs.purpose vocabulary: what kind of evidence a run represents.
# standalone and rolling_window are produced today; walk_forward_oos and
# final_holdout are reserved for the walk-forward optimizer (Program B). Kept in
# sync with the CHECK constraint in migration 0016.
BACKTEST_PURPOSE_STANDALONE = "standalone"
BACKTEST_PURPOSE_ROLLING_WINDOW = "rolling_window"
BACKTEST_PURPOSE_WALK_FORWARD_OOS = "walk_forward_oos"
BACKTEST_PURPOSE_FINAL_HOLDOUT = "final_holdout"


@dataclass
class BacktestConfig:
    account_name: str
    tickers_file: str
    universe_history_dir: str | None
    start: str | None
    end: str | None
    lookback_months: int | None
    slippage_bps: float
    fee_per_trade: float
    run_name: str | None
    allow_approximate_leaps: bool
    # Optional strategy override; None backtests the account's active strategy.
    strategy: str | None = None
    # Evidence kind persisted on the run; the walk-forward path overrides this
    # to rolling_window so its window runs are distinguishable from standalone.
    purpose: str = BACKTEST_PURPOSE_STANDALONE
    # Optional per-run parameter override for the resolved strategy. Used by the
    # walk-forward optimizer to evaluate grid candidates without mutating the
    # strategy catalog's params_json. Merged over the strategy's default params;
    # None runs the strategy's default (catalog) parameters.
    param_override: dict[str, Any] | None = None


@dataclass
class BacktestResult:
    run_id: int
    account_name: str
    start_date: str
    end_date: str
    tickers: list[str]
    trade_count: int
    ending_equity: float
    total_return_pct: float
    benchmark_return_pct: float | None
    alpha_pct: float | None
    max_drawdown_pct: float
    warnings: list[str]
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    avg_trade_return_pct: float | None = None

    def to_payload(
        self,
        *,
        display_name_fn: Callable[[str], str] | None = None,
    ) -> dict[str, object]:
        account_name = display_name_fn(self.account_name) if display_name_fn else self.account_name
        return {
            "runId": self.run_id,
            "accountName": account_name,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "tradeCount": self.trade_count,
            "endingEquity": self.ending_equity,
            "totalReturnPct": self.total_return_pct,
            "benchmarkReturnPct": self.benchmark_return_pct,
            "alphaPct": self.alpha_pct,
            "maxDrawdownPct": self.max_drawdown_pct,
            "annualizedReturnPct": self.annualized_return_pct,
            "sharpeRatio": self.sharpe_ratio,
            "sortinoRatio": self.sortino_ratio,
            "calmarRatio": self.calmar_ratio,
            "winRatePct": self.win_rate_pct,
            "profitFactor": self.profit_factor,
            "avgTradeReturnPct": self.avg_trade_return_pct,
            "warnings": self.warnings,
        }


@dataclass
class WalkForwardConfig:
    account_name: str
    tickers_file: str
    universe_history_dir: str | None
    start: str | None
    end: str | None
    lookback_months: int | None
    test_months: int
    step_months: int
    slippage_bps: float
    fee_per_trade: float
    run_name_prefix: str | None
    allow_approximate_leaps: bool


@dataclass
class WalkForwardSummary:
    account_name: str
    start_date: str
    end_date: str
    window_count: int
    run_ids: list[int]
    average_return_pct: float
    median_return_pct: float
    best_return_pct: float
    worst_return_pct: float

    def to_payload(
        self,
        *,
        display_name_fn: Callable[[str], str] | None = None,
    ) -> dict[str, object]:
        account_name = display_name_fn(self.account_name) if display_name_fn else self.account_name
        return {
            "accountName": account_name,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "windowCount": self.window_count,
            "runIds": self.run_ids,
            "averageReturnPct": self.average_return_pct,
            "medianReturnPct": self.median_return_pct,
            "bestReturnPct": self.best_return_pct,
            "worstReturnPct": self.worst_return_pct,
        }


@dataclass
class BacktestBatchConfig:
    account_names: list[str]
    tickers_file: str
    universe_history_dir: str | None
    start: str | None
    end: str | None
    lookback_months: int | None
    slippage_bps: float
    fee_per_trade: float
    run_name_prefix: str | None
    allow_approximate_leaps: bool
