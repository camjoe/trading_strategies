from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# backtest_runs.purpose vocabulary: what kind of evidence a run represents.
# standalone is the exploration corpus; walk_forward_oos and final_holdout are
# written by the walk-forward optimizer and are what promotion reads. Migration
# 0016's CHECK constraint still admits the retired 'rolling_window' value for
# historical rows; nothing writes it since the rolling-window path was removed.
BACKTEST_PURPOSE_STANDALONE = "standalone"
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
    # Evidence kind persisted on the run; the optimizer overrides this so its
    # window and holdout runs are distinguishable from standalone exploration.
    purpose: str = BACKTEST_PURPOSE_STANDALONE
    # Optional per-run parameter override for the resolved strategy. Used by the
    # walk-forward optimizer to evaluate grid candidates without mutating the
    # strategy catalog's params_json. Merged over the strategy's default params;
    # None runs the strategy's default (catalog) parameters.
    param_override: dict[str, Any] | None = None
    # Indicator warm-up lead-in: load this many months of price history *before*
    # the scoring window so signals are warm at the window start. These bars only
    # initialize indicators — returns, trades, and snapshots are measured from the
    # window start. 0 (default) preserves the original single-range behavior.
    warmup_months: int = 0


@dataclass(frozen=True)
class RunUniverse:
    """The tickers a run may touch, and how membership changes month to month.

    ``all_tickers`` is every ticker across every month, so price history is
    fetched once for the whole run; ``month_to_tickers`` is what each month is
    allowed to open positions in.
    """

    default_tickers: list[str]
    month_to_tickers: dict[str, list[str]]
    all_tickers: list[str]
    warnings: list[str]


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
