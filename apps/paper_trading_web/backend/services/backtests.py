from __future__ import annotations

from trading.backtesting.backtest import BacktestConfig

from ..schemas import BacktestPreflightRequest, BacktestRunRequest


def build_backtest_config_from_run_request(payload: BacktestRunRequest) -> BacktestConfig:
    return BacktestConfig(
        account_name=payload.account,
        tickers_file=payload.tickersFile,
        universe_history_dir=payload.universeHistoryDir,
        start=payload.start,
        end=payload.end,
        lookback_months=payload.lookbackMonths,
        slippage_bps=payload.slippageBps,
        fee_per_trade=payload.fee,
        run_name=payload.runName,
        allow_approximate_leaps=payload.allowApproximateLeaps,
    )


def build_backtest_config_from_preflight_request(payload: BacktestPreflightRequest) -> BacktestConfig:
    return BacktestConfig(
        account_name=payload.account,
        tickers_file=payload.tickersFile,
        universe_history_dir=payload.universeHistoryDir,
        start=payload.start,
        end=payload.end,
        lookback_months=payload.lookbackMonths,
        slippage_bps=0.0,
        fee_per_trade=0.0,
        run_name=None,
        allow_approximate_leaps=payload.allowApproximateLeaps,
    )
