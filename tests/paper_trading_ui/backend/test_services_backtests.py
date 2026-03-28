from __future__ import annotations

from paper_trading_ui.backend import services_backtests
from paper_trading_ui.backend.schemas import (
    BacktestPreflightRequest,
    BacktestRunRequest,
    WalkForwardRunRequest,
)


def test_build_backtest_config_from_run_request_maps_fields() -> None:
    payload = BacktestRunRequest(
        account="acct",
        tickersFile="tickers.txt",
        universeHistoryDir="history",
        start="2026-01-01",
        end="2026-02-01",
        lookbackMonths=2,
        slippageBps=7.5,
        fee=1.5,
        runName="run-abc",
        allowApproximateLeaps=True,
    )

    config = services_backtests.build_backtest_config_from_run_request(payload)
    assert config.account_name == "acct"
    assert config.tickers_file == "tickers.txt"
    assert config.universe_history_dir == "history"
    assert config.slippage_bps == 7.5
    assert config.fee_per_trade == 1.5
    assert config.allow_approximate_leaps is True


def test_build_backtest_config_from_preflight_request_zeroes_trading_costs() -> None:
    payload = BacktestPreflightRequest(account="acct", tickersFile="tickers.txt", allowApproximateLeaps=False)

    config = services_backtests.build_backtest_config_from_preflight_request(payload)
    assert config.account_name == "acct"
    assert config.tickers_file == "tickers.txt"
    assert config.slippage_bps == 0.0
    assert config.fee_per_trade == 0.0
    assert config.run_name is None


def test_build_walk_forward_config_from_request_maps_window_fields() -> None:
    payload = WalkForwardRunRequest(
        account="acct",
        tickersFile="tickers.txt",
        testMonths=3,
        stepMonths=2,
        runNamePrefix="wf",
        allowApproximateLeaps=True,
    )

    config = services_backtests.build_walk_forward_config_from_request(payload)
    assert config.account_name == "acct"
    assert config.test_months == 3
    assert config.step_months == 2
    assert config.run_name_prefix == "wf"
    assert config.allow_approximate_leaps is True
