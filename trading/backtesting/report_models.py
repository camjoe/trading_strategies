from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass
class BacktestReportSummary:
    run_id: int
    run_name: str | None
    account_name: str
    strategy: str
    start_date: str
    end_date: str
    created_at: str
    slippage_bps: float
    fee_per_trade: float
    tickers_file: str
    warnings: object
    trade_count: int
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    avg_trade_return_pct: float | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BacktestReportSummary":
        return cls(
            run_id=int(value["run_id"]),
            run_name=None if value.get("run_name") is None else str(value["run_name"]),
            account_name=str(value["account_name"]),
            strategy=str(value["strategy"]),
            start_date=str(value["start_date"]),
            end_date=str(value["end_date"]),
            created_at=str(value["created_at"]),
            slippage_bps=float(value["slippage_bps"]),
            fee_per_trade=float(value["fee_per_trade"]),
            tickers_file=str(value["tickers_file"]),
            warnings=value.get("warnings"),
            trade_count=int(value["trade_count"]),
            starting_equity=float(value["starting_equity"]),
            ending_equity=float(value["ending_equity"]),
            total_return_pct=float(value["total_return_pct"]),
            max_drawdown_pct=float(value["max_drawdown_pct"]),
            sharpe_ratio=None if value.get("sharpe_ratio") is None else float(value["sharpe_ratio"]),
            sortino_ratio=None if value.get("sortino_ratio") is None else float(value["sortino_ratio"]),
            calmar_ratio=None if value.get("calmar_ratio") is None else float(value["calmar_ratio"]),
            win_rate_pct=None if value.get("win_rate_pct") is None else float(value["win_rate_pct"]),
            profit_factor=None if value.get("profit_factor") is None else float(value["profit_factor"]),
            avg_trade_return_pct=(
                None if value.get("avg_trade_return_pct") is None else float(value["avg_trade_return_pct"])
            ),
        )


@dataclass
class BacktestLeaderboardEntry:
    run_id: int
    run_name: str | None
    account_name: str
    strategy: str
    start_date: str
    end_date: str
    created_at: str
    trade_count: int
    ending_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    benchmark_return_pct: float | None
    alpha_pct: float | None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    avg_trade_return_pct: float | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BacktestLeaderboardEntry":
        benchmark_return = value.get("benchmark_return_pct")
        alpha = value.get("alpha_pct")
        return cls(
            run_id=int(value["run_id"]),
            run_name=None if value.get("run_name") is None else str(value["run_name"]),
            account_name=str(value["account_name"]),
            strategy=str(value["strategy"]),
            start_date=str(value["start_date"]),
            end_date=str(value["end_date"]),
            created_at=str(value["created_at"]),
            trade_count=int(value["trade_count"]),
            ending_equity=float(value["ending_equity"]),
            total_return_pct=float(value["total_return_pct"]),
            max_drawdown_pct=float(value["max_drawdown_pct"]),
            benchmark_return_pct=None if benchmark_return is None else float(benchmark_return),
            alpha_pct=None if alpha is None else float(alpha),
            sharpe_ratio=None if value.get("sharpe_ratio") is None else float(value["sharpe_ratio"]),
            sortino_ratio=None if value.get("sortino_ratio") is None else float(value["sortino_ratio"]),
            calmar_ratio=None if value.get("calmar_ratio") is None else float(value["calmar_ratio"]),
            win_rate_pct=None if value.get("win_rate_pct") is None else float(value["win_rate_pct"]),
            profit_factor=None if value.get("profit_factor") is None else float(value["profit_factor"]),
            avg_trade_return_pct=(
                None if value.get("avg_trade_return_pct") is None else float(value["avg_trade_return_pct"])
            ),
        )


@dataclass
class BacktestReportSnapshot:
    snapshot_time: str
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class BacktestReportTrade:
    trade_time: str
    ticker: str
    side: str
    qty: float
    price: float
    fee: float


@dataclass
class BacktestFullReport:
    summary: BacktestReportSummary
    benchmark_ticker: str
    notes: object
    snapshots: list[BacktestReportSnapshot]
    trades: list[BacktestReportTrade]
    benchmark_return_pct: float | None
    alpha_pct: float | None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = asdict(self.summary)
        payload.update(
            {
                "benchmark_ticker": self.benchmark_ticker,
                "notes": self.notes,
                "snapshots": [asdict(item) for item in self.snapshots],
                "trades": [asdict(item) for item in self.trades],
                "benchmark_return_pct": self.benchmark_return_pct,
                "alpha_pct": self.alpha_pct,
            }
        )
        return payload
