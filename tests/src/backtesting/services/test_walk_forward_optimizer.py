"""Deterministic end-to-end orchestration of a walk-forward run.

Injects fake run functions so the winner is fixed by construction (no market data,
no DB), which lets the tests assert the honesty properties directly: selection uses
training data only, and OOS/holdout evidence is kept separate from it.
"""

from __future__ import annotations

import pytest

from backtesting.models import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestConfig,
    BacktestResult,
)
from backtesting.models.optimizer import FailureStage, OptimizerConfig
from backtesting.services.walk_forward_optimizer import (
    OptimizationRunError,
    run_walk_forward_optimization,
)
from trading.domain.exceptions import ValidationError

# The parameter set the fake engine makes clearly best on every training window. It
# differs from the "trend" default (fast_window=10) so the winner is provably a tuned
# variant, not the default.
GOOD_PARAMS = {"fast_window": 5, "slow_window": 20}


def _fake_result(cfg: BacktestConfig, *, annualized: float, drawdown: float, trades: int) -> BacktestResult:
    return BacktestResult(
        run_id=1,
        account_name=cfg.account_name,
        start_date=str(cfg.start),
        end_date=str(cfg.end),
        tickers=["AAPL"],
        trade_count=trades,
        ending_equity=1_000.0,
        total_return_pct=annualized,
        benchmark_return_pct=1.0,
        alpha_pct=annualized - 1.0,
        max_drawdown_pct=drawdown,
        warnings=[],
        annualized_return_pct=annualized,
        calmar_ratio=(annualized / abs(drawdown) if drawdown else None),
    )


def _metrics_for(cfg: BacktestConfig) -> tuple[float, float, int]:
    override = cfg.param_override
    if override is None:
        return (5.0, -10.0, 10)  # default-parameter baseline
    if override == GOOD_PARAMS:
        return (30.0, -5.0, 12)  # unambiguous winner
    return (8.0, -12.0, 8)  # other grid candidates


def _orchestration_cfg() -> OptimizerConfig:
    return OptimizerConfig(
        account_name="acct_opt",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        strategy="trend",
        search_space={"fast_window": [5, 10], "slow_window": [20, 30]},
        start="2022-01-01",
        end="2023-12-31",
        lookback_months=None,
        slippage_bps=0.0,
        fee_per_trade=0.0,
        allow_approximate_leaps=False,
        train_months=6,
        test_months=1,
        step_months=1,
        holdout_months=3,
    )


class TestOptimizerOrchestration:
    def _run(self):
        cfg = _orchestration_cfg()
        persisted: list[BacktestConfig] = []
        metrics_only: list[BacktestConfig] = []

        def fake_metrics(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            metrics_only.append(run_cfg)
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        def fake_persisted(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            persisted.append(run_cfg)
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        summary = run_walk_forward_optimization(
            None,
            cfg,
            run_metrics_only_fn=fake_metrics,
            run_persisted_fn=fake_persisted,
        )
        return cfg, summary, persisted, metrics_only

    def test_selects_winner_on_every_window(self) -> None:
        _cfg, summary, _persisted, _metrics = self._run()
        assert summary.windows
        assert all(w.winner.params == GOOD_PARAMS for w in summary.windows)
        # The tuned winner differs from the strategy default and beats the baseline OOS.
        assert summary.default_params == {"fast_window": 10, "slow_window": 20}
        assert all(w.winner_oos.total_return_pct > w.baseline_oos.total_return_pct for w in summary.windows)

    def test_windows_carry_every_evaluated_candidate(self) -> None:
        # The full attempted search is carried on each window (not just the winner) so
        # it can be persisted as the per-window multiple-testing audit record.
        _cfg, summary, _persisted, _metrics = self._run()
        candidate_count = 4  # 2 x 2 grid
        for window in summary.windows:
            assert len(window.candidates) == candidate_count
            assert sum(1 for c in window.candidates if c.params == GOOD_PARAMS) == 1
            assert window.winner in window.candidates

    def test_risk_metrics_propagate_into_outcomes(self) -> None:
        # Drawdown and calmar reach the reported OOS outcomes so the summary can judge
        # risk-adjusted performance, not just total return.
        _cfg, summary, _persisted, _metrics = self._run()
        winner_oos = summary.windows[0].winner_oos
        assert winner_oos.max_drawdown_pct == -5.0  # GOOD_PARAMS drawdown
        assert winner_oos.calmar_ratio == 30.0 / 5.0
        assert summary.windows[0].baseline_oos.max_drawdown_pct == -10.0  # default baseline

    def test_selection_uses_training_data_only(self) -> None:
        _cfg, summary, persisted, metrics_only = self._run()
        candidate_count = 4  # 2 x 2 grid
        # Every persisted run is OOS or holdout evidence carrying the winner's params;
        # training trials never persist (they only ever hit the metrics-only path).
        assert persisted, "expected persisted OOS/holdout runs"
        for run_cfg in persisted:
            assert run_cfg.purpose in {BACKTEST_PURPOSE_WALK_FORWARD_OOS, BACKTEST_PURPOSE_FINAL_HOLDOUT}
            assert run_cfg.param_override == GOOD_PARAMS
        # Every grid candidate was evaluated on each window's training interval via the
        # metrics-only path (standalone purpose, a concrete param override, not persisted).
        training_runs = [
            c for c in metrics_only if c.purpose == BACKTEST_PURPOSE_STANDALONE and c.param_override is not None
        ]
        assert len(training_runs) == len(summary.windows) * candidate_count
        oos = [c for c in persisted if c.purpose == BACKTEST_PURPOSE_WALK_FORWARD_OOS]
        assert len(oos) == len(summary.windows)

    def test_holdout_carries_last_winner_and_is_persisted(self) -> None:
        _cfg, summary, persisted, _metrics = self._run()
        assert summary.holdout is not None
        assert summary.holdout.winner_params == GOOD_PARAMS
        assert summary.holdout.winner.total_return_pct > summary.holdout.baseline.total_return_pct
        holdout_runs = [c for c in persisted if c.purpose == BACKTEST_PURPOSE_FINAL_HOLDOUT]
        assert len(holdout_runs) == 1
        assert holdout_runs[0].start == summary.holdout.holdout_start.isoformat()

    def test_rejects_search_space_with_unknown_parameter(self) -> None:
        cfg = OptimizerConfig(
            account_name="acct_opt",
            tickers_file="tickers.txt",
            universe_history_dir=None,
            strategy="trend",
            search_space={"not_a_param": [1, 2]},
            start="2022-01-01",
            end="2023-12-31",
            lookback_months=None,
            slippage_bps=0.0,
            fee_per_trade=0.0,
            allow_approximate_leaps=False,
        )
        with pytest.raises(ValidationError, match="not parameters of strategy"):
            run_walk_forward_optimization(
                None, cfg, run_metrics_only_fn=lambda *_: None, run_persisted_fn=lambda *_: None
            )

    def test_window_search_failure_raises_optimization_run_error_with_context(self) -> None:
        # The second window's persisted OOS run blows up; the first window already
        # completed. The error should say so, so a failed-experiment row can record it.
        cfg = _orchestration_cfg()
        oos_calls = 0

        def fake_metrics(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        def failing_persisted(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            nonlocal oos_calls
            oos_calls += 1
            if oos_calls == 2:
                raise RuntimeError("simulated market-data outage")
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        with pytest.raises(OptimizationRunError) as exc_info:
            run_walk_forward_optimization(
                None, cfg, run_metrics_only_fn=fake_metrics, run_persisted_fn=failing_persisted
            )
        error = exc_info.value
        assert error.stage == FailureStage.WINDOW_SEARCH
        assert error.windows_completed == 1
        assert "simulated market-data outage" in error.cause_message

    def test_holdout_failure_raises_optimization_run_error_with_full_window_count(self) -> None:
        cfg = _orchestration_cfg()

        def fake_metrics(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        def failing_on_holdout_persisted(_conn, run_cfg: BacktestConfig) -> BacktestResult:
            if run_cfg.purpose == BACKTEST_PURPOSE_FINAL_HOLDOUT:
                raise RuntimeError("simulated holdout failure")
            ann, dd, trades = _metrics_for(run_cfg)
            return _fake_result(run_cfg, annualized=ann, drawdown=dd, trades=trades)

        # Every window must complete before the holdout stage runs at all.
        expected_window_count = len(
            run_walk_forward_optimization(
                None, cfg, run_metrics_only_fn=fake_metrics, run_persisted_fn=fake_metrics
            ).windows
        )

        with pytest.raises(OptimizationRunError) as exc_info:
            run_walk_forward_optimization(
                None, cfg, run_metrics_only_fn=fake_metrics, run_persisted_fn=failing_on_holdout_persisted
            )
        error = exc_info.value
        assert error.stage == FailureStage.HOLDOUT
        assert error.windows_completed == expected_window_count
