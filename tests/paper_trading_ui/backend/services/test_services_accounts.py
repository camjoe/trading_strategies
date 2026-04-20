from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from common.time import utc_now_iso
from paper_trading_ui.backend.services import accounts as services_accounts
from paper_trading_ui.backend.services.accounts import backtests as account_backtests
from paper_trading_ui.backend.services.accounts import benchmark as account_benchmark
from paper_trading_ui.backend.services.accounts import summaries as account_summaries
from paper_trading_ui.backend.config import (
    TEST_ACCOUNT_NAME,
    TEST_ACCOUNT_STRATEGY,
    TEST_BACKTEST_ACCOUNT_NAME,
)
from trading.models.account_state import AccountState


def test_build_account_summary_uses_snapshot_delta(monkeypatch) -> None:
    monkeypatch.setattr(
        account_summaries,
        "build_account_stats",
        lambda _conn, _row: (None, None, None, None, 1200.0),
    )
    monkeypatch.setattr(
        account_summaries,
        "fetch_latest_snapshot_row",
        lambda _conn, _account_id: {"equity": 1100.0, "snapshot_time": "2026-01-02T00:00:00Z"},
    )

    summary = services_accounts.build_account_summary(
        conn=None,
        row={
            "id": 1,
            "name": "acct_a",
            "descriptive_name": "Account A",
            "strategy": "trend",
            "instrument_mode": "equity",
            "risk_policy": "none",
            "benchmark_ticker": "SPY",
            "initial_cash": 1000.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "goal_min_return_pct": None,
            "goal_max_return_pct": None,
            "goal_period": None,
            "learning_enabled": None,
            "option_strike_offset_pct": None,
            "option_min_dte": None,
            "option_max_dte": None,
            "option_type": None,
            "target_delta_min": None,
            "target_delta_max": None,
            "max_premium_per_trade": None,
            "max_contracts_per_trade": None,
            "iv_rank_min": None,
            "iv_rank_max": None,
            "roll_dte_threshold": None,
            "profit_take_pct": None,
            "max_loss_pct": None,
        },
    )

    assert summary["equity"] == 1200.0
    assert summary["totalChange"] == 200.0
    assert summary["totalChangePct"] == pytest.approx(20.0)
    assert summary["changeSinceLastSnapshot"] == 100.0


def test_build_live_benchmark_overlay_aligns_snapshot_period(monkeypatch) -> None:
    close_index = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"])
    close_series = pd.Series([100.0, 105.0, 110.0], index=close_index)
    monkeypatch.setattr(
        account_benchmark,
        "fetch_benchmark_close_history",
        lambda _ticker, *, start_date, end_date: close_series,
    )

    overlay = services_accounts.build_live_benchmark_overlay(
        {"benchmark": "SPY", "equity": 1200.0},
        [
            {"snapshot_time": "2026-01-04T00:00:00Z", "equity": 1200.0},
            {"snapshot_time": "2026-01-02T00:00:00Z", "equity": 1000.0},
            {"snapshot_time": "2026-01-03T00:00:00Z", "equity": 1100.0},
        ],
    )

    assert overlay is not None
    assert overlay["benchmark"] == "SPY"
    assert overlay["startTime"] == "2026-01-02T00:00:00Z"
    assert overlay["endTime"] == "2026-01-04T00:00:00Z"
    assert overlay["benchmarkReturnPct"] == pytest.approx(10.0)
    assert overlay["alphaPct"] == pytest.approx(10.0)
    points = overlay["points"]
    assert len(points) == 3
    assert points[-1]["benchmarkEquity"] == pytest.approx(1100.0)


def test_attach_live_benchmark_summary_sets_fields() -> None:
    summary = {"name": "acct"}
    overlay = {
        "benchmarkReturnPct": 6.0,
        "alphaPct": 2.5,
        "benchmarkEquity": 1060.0,
        "startTime": "2026-01-01T00:00:00Z",
        "endTime": "2026-01-10T00:00:00Z",
    }

    services_accounts.attach_live_benchmark_summary(summary, overlay)

    assert summary["liveBenchmarkReturnPct"] == pytest.approx(6.0)
    assert summary["liveAlphaPct"] == pytest.approx(2.5)
    assert summary["liveBenchmarkEquity"] == pytest.approx(1060.0)
    assert summary["liveBenchmarkStartTime"] == "2026-01-01T00:00:00Z"
    assert summary["liveBenchmarkEndTime"] == "2026-01-10T00:00:00Z"


def test_display_helpers_map_shadow_backtest_account() -> None:
    assert services_accounts.display_account_name(TEST_BACKTEST_ACCOUNT_NAME) == TEST_ACCOUNT_NAME
    assert services_accounts.display_account_name("acct_live") == "acct_live"
    assert services_accounts.display_strategy(TEST_BACKTEST_ACCOUNT_NAME, "trend") == TEST_ACCOUNT_STRATEGY
    assert services_accounts.display_strategy("acct_live", "trend") == "trend"


def test_build_backtest_run_summary_uses_display_transforms() -> None:
    run_dict = {
        "runId": 7,
        "runName": "run-shadow",
        "accountName": TEST_BACKTEST_ACCOUNT_NAME,
        "strategy": "trend",
        "startDate": "2026-01-01",
        "endDate": "2026-01-31",
        "createdAt": "2026-02-01T00:00:00Z",
        "slippageBps": 5.0,
        "feePerTrade": 1.25,
        "tickersFile": "trading/config/trade_universe.txt",
    }

    payload = account_backtests._apply_display_names(run_dict)
    assert payload["runId"] == 7
    assert payload["accountName"] == TEST_ACCOUNT_NAME
    assert payload["strategy"] == TEST_ACCOUNT_STRATEGY
    assert payload["feePerTrade"] == 1.25


def test_fetch_managed_account_rows_excludes_shadow_account(conn, create_test_account) -> None:
    create_test_account("acct_one")
    create_test_account(TEST_BACKTEST_ACCOUNT_NAME)
    create_test_account("acct_two")

    rows = services_accounts.fetch_managed_account_rows(conn)
    names = [str(row["name"]) for row in rows]
    assert names == ["acct_one", "acct_two"]


def test_fetch_latest_backtest_summary_none_and_present(conn, create_test_account) -> None:
    account_id = create_test_account("acct_bt")

    assert services_accounts.fetch_latest_backtest_summary(conn, "acct_bt") is None

    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "run-1", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.25, "trading/config/trade_universe.txt"),
    )
    conn.commit()

    summary = services_accounts.fetch_latest_backtest_summary(conn, "acct_bt")
    assert summary is not None
    assert summary["runName"] == "run-1"
    assert summary["accountName"] == "acct_bt"


def test_fetch_latest_backtest_metrics_uses_summary_report(monkeypatch, conn, create_test_account) -> None:
    account_id = create_test_account("acct_metrics")
    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "run-metrics", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.0, "trading/config/trade_universe.txt"),
    )
    conn.commit()

    monkeypatch.setattr(
        account_backtests,
        "fetch_backtest_report_summary",
        lambda _conn, _run_id: SimpleNamespace(
            run_id=99,
            end_date="2026-01-31",
            total_return_pct=12.5,
            max_drawdown_pct=-4.2,
            sharpe_ratio=1.4,
            sortino_ratio=1.9,
            calmar_ratio=0.8,
            win_rate_pct=57.0,
            profit_factor=1.6,
            avg_trade_return_pct=2.1,
        ),
    )

    payload = services_accounts.fetch_latest_backtest_metrics(conn, "acct_metrics")
    assert payload == {
        "runId": 99,
        "endDate": "2026-01-31",
        "totalReturnPct": 12.5,
        "maxDrawdownPct": -4.2,
        "sharpeRatio": 1.4,
        "sortinoRatio": 1.9,
        "calmarRatio": 0.8,
        "winRatePct": 57.0,
        "profitFactor": 1.6,
        "avgTradeReturnPct": 2.1,
    }


def test_build_comparison_account_payload_includes_live_overlay_summary() -> None:
    payload = services_accounts.build_comparison_account_payload(
        {
            "name": "acct_cmp",
            "displayName": "Acct Compare",
            "strategy": "trend",
            "benchmark": "SPY",
            "equity": 1100.0,
            "initialCash": 1000.0,
            "totalChange": 100.0,
            "totalChangePct": 10.0,
            "liveBenchmarkReturnPct": 7.0,
            "liveAlphaPct": 3.0,
        },
        None,
    )

    assert payload["liveBenchmarkReturnPct"] == pytest.approx(7.0)
    assert payload["liveAlphaPct"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# _build_positions_from_stats
# ---------------------------------------------------------------------------

def _make_state(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    *,
    cash: float = 0.0,
    realized_pnl: float = 0.0,
    total_deposited: float = 0.0,
) -> AccountState:
    return AccountState(
        cash=cash,
        positions=positions,
        avg_cost=avg_cost,
        realized_pnl=realized_pnl,
        total_deposited=total_deposited,
    )


class TestBuildPositionsFromStats:
    def test_missing_price_skips_position(self) -> None:
        """Regression: price unavailable must skip, not produce a negative PnL."""
        state = _make_state({"AAPL": 5.0}, {"AAPL": 100.0})
        positions = services_accounts._build_positions_from_stats(state, {})
        assert positions == []

    def test_partial_prices_skips_only_missing(self) -> None:
        state = _make_state({"AAPL": 2.0, "MSFT": 3.0}, {"AAPL": 100.0, "MSFT": 200.0})
        positions = services_accounts._build_positions_from_stats(state, {"AAPL": 110.0})
        tickers = [p["ticker"] for p in positions]
        assert tickers == ["AAPL"]
        assert "MSFT" not in tickers

    def test_unrealized_pnl_formula(self) -> None:
        """unrealizedPnl = (marketPrice - avgCost) * qty."""
        state = _make_state({"AAPL": 4.0}, {"AAPL": 100.0})
        positions = services_accounts._build_positions_from_stats(state, {"AAPL": 110.0})
        assert len(positions) == 1
        pos = positions[0]
        assert pos["unrealizedPnl"] == pytest.approx((110.0 - 100.0) * 4.0)
        assert pos["marketValue"] == pytest.approx(110.0 * 4.0)
        assert pos["avgCost"] == pytest.approx(100.0)

    def test_settlement_ticker_excluded(self) -> None:
        from common.constants import SETTLEMENT_TICKER
        state = _make_state(
            {"AAPL": 2.0, SETTLEMENT_TICKER: 500.0},
            {"AAPL": 100.0},
        )
        positions = services_accounts._build_positions_from_stats(
            state, {"AAPL": 105.0, SETTLEMENT_TICKER: 1.0}
        )
        tickers = [p["ticker"] for p in positions]
        assert SETTLEMENT_TICKER not in tickers
        assert "AAPL" in tickers

    def test_zero_qty_excluded(self) -> None:
        state = _make_state({"AAPL": 0.0, "MSFT": 2.0}, {"MSFT": 50.0})
        positions = services_accounts._build_positions_from_stats(
            state, {"AAPL": 100.0, "MSFT": 60.0}
        )
        assert len(positions) == 1
        assert positions[0]["ticker"] == "MSFT"

    def test_negative_unrealized_pnl_when_price_falls(self) -> None:
        state = _make_state({"AAPL": 3.0}, {"AAPL": 100.0})
        positions = services_accounts._build_positions_from_stats(state, {"AAPL": 90.0})
        assert positions[0]["unrealizedPnl"] == pytest.approx((90.0 - 100.0) * 3.0)


# ---------------------------------------------------------------------------
# build_account_summary — key fields present
# ---------------------------------------------------------------------------

class TestBuildAccountSummaryShape:
    def test_required_keys_present(self, monkeypatch) -> None:
        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            lambda _conn, _row: (None, None, None, None, 1200.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "fetch_latest_snapshot_row",
            lambda _conn, _account_id: None,
        )
        row = {
            "id": 1,
            "name": "acct_shape",
            "descriptive_name": "Shape Account",
            "strategy": "trend",
            "instrument_mode": "equity",
            "risk_policy": "none",
            "benchmark_ticker": "SPY",
            "initial_cash": 1000.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "goal_min_return_pct": None,
            "goal_max_return_pct": None,
            "goal_period": None,
            "learning_enabled": None,
            "option_strike_offset_pct": None,
            "option_min_dte": None,
            "option_max_dte": None,
            "option_type": None,
            "target_delta_min": None,
            "target_delta_max": None,
            "max_premium_per_trade": None,
            "max_contracts_per_trade": None,
            "iv_rank_min": None,
            "iv_rank_max": None,
            "roll_dte_threshold": None,
            "profit_take_pct": None,
            "max_loss_pct": None,
        }
        summary = services_accounts.build_account_summary(conn=None, row=row)
        for key in ("name", "equity", "initialCash", "totalChange",
                    "totalChangePct", "changeSinceLastSnapshot", "strategy"):
            assert key in summary, f"Missing key: {key}"

    def test_rotation_keys_present_and_parsed(self, monkeypatch) -> None:
        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            lambda _conn, _row: (None, None, None, None, 1200.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "fetch_latest_snapshot_row",
            lambda _conn, _account_id: None,
        )
        row = {
            "id": 1,
            "name": "acct_rotation",
            "descriptive_name": "Rotation Account",
            "strategy": "trend",
            "instrument_mode": "equity",
            "risk_policy": "none",
            "benchmark_ticker": "SPY",
            "initial_cash": 1000.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "goal_min_return_pct": None,
            "goal_max_return_pct": None,
            "goal_period": None,
            "learning_enabled": None,
            "option_strike_offset_pct": None,
            "option_min_dte": None,
            "option_max_dte": None,
            "option_type": None,
            "target_delta_min": None,
            "target_delta_max": None,
            "max_premium_per_trade": None,
            "max_contracts_per_trade": None,
            "iv_rank_min": None,
            "iv_rank_max": None,
            "roll_dte_threshold": None,
            "profit_take_pct": None,
            "max_loss_pct": None,
            "rotation_enabled": 1,
            "rotation_mode": "optimal",
            "rotation_optimality_mode": "average_return",
            "rotation_interval_days": 7,
            "rotation_interval_minutes": 240,
            "rotation_lookback_days": 30,
            "rotation_schedule": '["trend","ma_crossover","mean_reversion"]',
            "rotation_regime_strategy_risk_on": "trend",
            "rotation_regime_strategy_neutral": "ma_crossover",
            "rotation_regime_strategy_risk_off": "mean_reversion",
            "rotation_overlay_mode": "news_social",
            "rotation_overlay_min_tickers": 3,
            "rotation_overlay_confidence_threshold": 0.65,
            "rotation_overlay_watchlist": '["AAPL","MSFT","NVDA"]',
            "rotation_active_index": 1,
            "rotation_active_strategy": "ma_crossover",
            "rotation_last_at": "2026-03-20T00:00:00Z",
        }

        summary = services_accounts.build_account_summary(conn=None, row=row)
        assert summary["rotationEnabled"] is True
        assert summary["rotationMode"] == "optimal"
        assert summary["rotationOptimalityMode"] == "average_return"
        assert summary["rotationIntervalDays"] == 7
        assert summary["rotationIntervalMinutes"] == 240
        assert summary["rotationLookbackDays"] == 30
        assert summary["rotationSchedule"] == ["trend", "ma_crossover", "mean_reversion"]
        assert summary["rotationRegimeStrategyRiskOn"] == "trend"
        assert summary["rotationRegimeStrategyNeutral"] == "ma_crossover"
        assert summary["rotationRegimeStrategyRiskOff"] == "mean_reversion"
        assert summary["rotationOverlayMode"] == "news_social"
        assert summary["rotationOverlayMinTickers"] == 3
        assert summary["rotationOverlayConfidenceThreshold"] == pytest.approx(0.65)
        assert summary["rotationOverlayWatchlist"] == ["AAPL", "MSFT", "NVDA"]
        assert summary["rotationActiveIndex"] == 1
        assert summary["rotationLastAt"] == "2026-03-20T00:00:00Z"
        assert summary["rotationActiveStrategy"] == "ma_crossover"

    def test_deposit_model_account_zero_initial_cash(self, monkeypatch) -> None:
        """zero initial_cash + no snapshot → delta_pct = 0.0 (no crash)."""
        monkeypatch.setattr(
            account_summaries,
            "build_account_stats",
            lambda _conn, _row: (None, None, None, None, 1100.0),
        )
        monkeypatch.setattr(
            account_summaries,
            "fetch_latest_snapshot_row",
            lambda _conn, _account_id: None,
        )
        row = {
            "id": 2,
            "name": "deposit_acct",
            "descriptive_name": "Deposit",
            "strategy": "trend",
            "instrument_mode": "equity",
            "risk_policy": "none",
            "benchmark_ticker": "SPY",
            "initial_cash": 0.0,
            "stop_loss_pct": None, "take_profit_pct": None,
            "goal_min_return_pct": None, "goal_max_return_pct": None,
            "goal_period": None, "learning_enabled": None,
            "option_strike_offset_pct": None, "option_min_dte": None,
            "option_max_dte": None, "option_type": None,
            "target_delta_min": None, "target_delta_max": None,
            "max_premium_per_trade": None, "max_contracts_per_trade": None,
            "iv_rank_min": None, "iv_rank_max": None,
            "roll_dte_threshold": None, "profit_take_pct": None,
            "max_loss_pct": None,
        }
        summary = services_accounts.build_account_summary(conn=None, row=row)
        assert summary["totalChangePct"] == pytest.approx(0.0)
