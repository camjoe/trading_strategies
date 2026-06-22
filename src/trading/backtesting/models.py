from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
