"""Walk-forward optimizer: pure-domain unit tests plus a deterministic end-to-end
orchestration test that injects fake run functions so the winner is fixed by
construction (no market data, no DB). The end-to-end test asserts the honesty
properties: selection uses training data only, and OOS/holdout evidence is separate."""

from __future__ import annotations

from datetime import date

import pytest

from trading.backtesting.domain.optimization.objective import (
    MAX_DRAWDOWN_ELIGIBILITY_PCT,
    MIN_CANDIDATE_TRADES,
    calmar_v1_score,
    evaluate_candidate,
    select_winner,
)
from trading.backtesting.domain.optimization.search import generate_candidates
from trading.backtesting.domain.windowing import build_walk_forward_optimization_splits
from trading.backtesting.models import (
    BACKTEST_PURPOSE_FINAL_HOLDOUT,
    BACKTEST_PURPOSE_STANDALONE,
    BACKTEST_PURPOSE_WALK_FORWARD_OOS,
    BacktestConfig,
    BacktestResult,
)
from trading.backtesting.optimizer_models import OptimizerConfig
from trading.backtesting.services.walk_forward_optimizer_service import (
    run_walk_forward_optimization,
)
from trading.domain.exceptions import ValidationError

# The parameter set the fake engine makes clearly best on every training window. It
# differs from the "trend" default (fast_window=10) so the winner is provably a tuned
# variant, not the default.
GOOD_PARAMS = {"fast_window": 5, "slow_window": 20}


class TestGridSearch:
    def test_generates_canonical_ordered_product(self) -> None:
        candidates = generate_candidates({"fast_window": [5, 10], "slow_window": [20, 30]}, budget=256)
        assert candidates == [
            {"fast_window": 5, "slow_window": 20},
            {"fast_window": 5, "slow_window": 30},
            {"fast_window": 10, "slow_window": 20},
            {"fast_window": 10, "slow_window": 30},
        ]

    def test_rejects_grid_over_budget(self) -> None:
        with pytest.raises(ValidationError, match="exceeds candidate budget"):
            generate_candidates({"a": [1, 2, 3], "b": [1, 2, 3]}, budget=8)

    def test_rejects_empty_space_and_empty_values(self) -> None:
        with pytest.raises(ValidationError):
            generate_candidates({}, budget=8)
        with pytest.raises(ValidationError):
            generate_candidates({"a": []}, budget=8)


class TestObjective:
    def test_calmar_v1_floor_keeps_low_drawdown_finite(self) -> None:
        # Drawdown magnitude below the 1pp floor uses the floor as denominator.
        assert calmar_v1_score(annualized_return_pct=10.0, max_drawdown_pct=-0.2) == 10.0

    def test_rejects_too_few_trades(self) -> None:
        result = evaluate_candidate(
            index=0,
            params={"x": 1},
            annualized_return_pct=20.0,
            max_drawdown_pct=-5.0,
            trade_count=MIN_CANDIDATE_TRADES - 1,
        )
        assert not result.eligible
        assert result.score is None
        assert "too_few_trades" in result.rejection_reason

    def test_negative_return_is_eligible_but_scored_low(self) -> None:
        # The positive-return training gate was intentionally dropped: a down-regime
        # candidate stays selectable (best-of-field) and its OOS/holdout run is the judge.
        result = evaluate_candidate(
            index=0, params={}, annualized_return_pct=-8.0, max_drawdown_pct=-5.0, trade_count=10
        )
        assert result.eligible
        assert result.score is not None and result.score < 0

    def test_rejects_missing_return_and_excess_drawdown(self) -> None:
        missing = evaluate_candidate(
            index=0, params={}, annualized_return_pct=None, max_drawdown_pct=-5.0, trade_count=10
        )
        assert missing.rejection_reason == "no_annualized_return"
        deep = evaluate_candidate(
            index=1,
            params={},
            annualized_return_pct=10.0,
            max_drawdown_pct=MAX_DRAWDOWN_ELIGIBILITY_PCT - 1.0,
            trade_count=10,
        )
        assert "drawdown_exceeds_limit" in deep.rejection_reason

    def test_select_winner_ranks_by_score_then_tiebreaks(self) -> None:
        results = [
            evaluate_candidate(
                index=0, params={"n": 0}, annualized_return_pct=8.0, max_drawdown_pct=-12.0, trade_count=8
            ),
            evaluate_candidate(
                index=1, params={"n": 1}, annualized_return_pct=30.0, max_drawdown_pct=-5.0, trade_count=12
            ),
            evaluate_candidate(
                index=2, params={"n": 2}, annualized_return_pct=8.0, max_drawdown_pct=-12.0, trade_count=8
            ),
        ]
        assert select_winner(results).params == {"n": 1}

    def test_select_winner_raises_when_none_eligible(self) -> None:
        # Ineligible via a still-active gate (too few trades); the error names the reason.
        results = [
            evaluate_candidate(index=0, params={}, annualized_return_pct=5.0, max_drawdown_pct=-5.0, trade_count=1),
        ]
        with pytest.raises(ValidationError, match="No eligible candidate.*too_few_trades"):
            select_winner(results)


class TestWindowSplits:
    def test_training_precedes_test_and_holdout_is_isolated(self) -> None:
        splits, holdout = build_walk_forward_optimization_splits(
            date(2022, 1, 1),
            date(2024, 12, 31),
            train_months=12,
            test_months=1,
            step_months=1,
            holdout_months=6,
        )
        assert holdout == (date(2024, 7, 1), date(2024, 12, 31))
        assert splits, "expected at least one split"
        for split in splits:
            assert split.train_end < split.test_start
            assert split.test_end < holdout[0]

    def test_rejects_overlapping_oos_windows(self) -> None:
        with pytest.raises(ValidationError, match="overlapping OOS"):
            build_walk_forward_optimization_splits(
                date(2022, 1, 1),
                date(2024, 12, 31),
                train_months=12,
                test_months=3,
                step_months=1,
                holdout_months=6,
            )


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
    )


def _metrics_for(cfg: BacktestConfig) -> tuple[float, float, int]:
    override = cfg.param_override
    if override is None:
        return (5.0, -10.0, 10)  # default-parameter baseline
    if override == GOOD_PARAMS:
        return (30.0, -5.0, 12)  # unambiguous winner
    return (8.0, -12.0, 8)  # other grid candidates


class TestOptimizerOrchestration:
    def _run(self):
        cfg = OptimizerConfig(
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
