"""Operational optimize -> promote loop: persistence of an experiment and promotion
of its winner into a tradeable, frozen strategy variant.

The optimizer is driven with fake run functions so the winner is fixed by
construction; the persisted OOS/holdout runs are real ``backtest_runs`` rows so the
experiment's ``holdout_run_id`` foreign key is satisfied.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from tests.support.repositories import insert_repository_account
from trading.backtesting.domain.optimization.search import params_fingerprint
from trading.backtesting.models import BacktestConfig, BacktestResult
from trading.backtesting.optimizer_models import OptimizationExperimentInsert, OptimizerConfig
from trading.backtesting.repositories.backtest_repository import insert_backtest_run
from trading.backtesting.repositories.optimization_repository import (
    fetch_experiment_by_id,
    fetch_manifest_for_experiment,
    fetch_trials_for_experiment,
    fetch_windows_for_experiment,
    insert_experiment,
)
from trading.backtesting.services.walk_forward_optimizer_service import run_and_persist_optimization
from trading.domain.exceptions import NotFoundError
from trading.services.profiles.source import DEFAULT_TICKERS_FILE
from trading.services.strategy_catalog.optimizer_promotion import promote_optimization_experiment

# The winning candidate (differs from trend's default fast/slow, so the promoted
# variant is provably a tuned variant, not the default).
WINNER = {"slow_window": 40}


def _fake_result(
    cfg: BacktestConfig, *, run_id: int, annualized: float, drawdown: float, trades: int
) -> BacktestResult:
    return BacktestResult(
        run_id=run_id,
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
    if override == WINNER:
        return (30.0, -5.0, 12)  # unambiguous winner
    return (8.0, -12.0, 8)  # the other grid candidate


def _run_and_persist(conn, account_id: int, *, account_name: str) -> int:
    cfg = OptimizerConfig(
        account_name=account_name,
        # A real universe file so the run manifest's universe resolution succeeds
        # (the fake run functions never read it, but manifest capture does).
        tickers_file=DEFAULT_TICKERS_FILE,
        universe_history_dir=None,
        strategy="trend",
        search_space={"slow_window": [20, 40]},
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

    def fake_metrics(_conn, run_cfg: BacktestConfig) -> BacktestResult:
        ann, dd, trades = _metrics_for(run_cfg)
        return _fake_result(run_cfg, run_id=0, annualized=ann, drawdown=dd, trades=trades)

    def fake_persisted(run_conn, run_cfg: BacktestConfig) -> BacktestResult:
        # Persisted OOS/holdout runs are real rows so holdout_run_id FK is valid.
        run_id = insert_backtest_run(
            run_conn,
            account_id=account_id,
            strategy_name=run_cfg.strategy,
            start_date=date.fromisoformat(str(run_cfg.start)),
            end_date=date.fromisoformat(str(run_cfg.end)),
            cfg=run_cfg,
            warnings=[],
        )
        ann, dd, trades = _metrics_for(run_cfg)
        return _fake_result(run_cfg, run_id=run_id, annualized=ann, drawdown=dd, trades=trades)

    summary = run_and_persist_optimization(
        conn, cfg, run_metrics_only_fn=fake_metrics, run_persisted_fn=fake_persisted
    )
    assert summary.experiment_id is not None
    return summary.experiment_id


class TestPersistence:
    def test_run_persists_experiment_with_winner_and_holdout(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_persist")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_persist")

        record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
        assert record is not None
        assert record.account_id == account_id
        assert record.primitive == "trend"
        assert json.loads(record.winner_params_json) == WINNER
        # Winner beat the baseline on every OOS window in this fixture.
        assert record.oos_windows_beat_baseline == record.window_count
        assert record.oos_mean_winner_return_pct == pytest.approx(30.0)
        assert record.holdout_run_id is not None  # real persisted holdout run
        assert record.promoted_strategy_id is None

    def test_run_persists_per_window_and_per_candidate_audit(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_audit")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_audit")

        record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
        windows = fetch_windows_for_experiment(conn, experiment_id=experiment_id)
        trials = fetch_trials_for_experiment(conn, experiment_id=experiment_id)
        assert record is not None

        # One window row per walk-forward window, in order, each linked to a real OOS run.
        assert len(windows) == record.window_count
        assert [w.window_index for w in windows] == list(range(1, record.window_count + 1))
        assert all(w.oos_run_id is not None for w in windows)

        # Every grid candidate (the 2-point slow_window grid) is persisted per window —
        # the multiple-testing record, not just the winner.
        trials_by_window: dict[int, list] = {}
        for trial in trials:
            trials_by_window.setdefault(trial.window_id, []).append(trial)
        for window in windows:
            window_trials = trials_by_window[window.id]
            assert len(window_trials) == 2
            selected = [t for t in window_trials if t.selected]
            assert len(selected) == 1  # exactly one winner per window
            assert json.loads(selected[0].params_json) == WINNER
            assert selected[0].params_hash == params_fingerprint(WINNER)
            # Hashes are distinct per candidate (the one-hash-per-window invariant).
            assert len({t.params_hash for t in window_trials}) == len(window_trials)

    def test_run_persists_frozen_provenance_manifest(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_manifest_e2e")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_manifest_e2e")

        manifest = fetch_manifest_for_experiment(conn, experiment_id=experiment_id)
        assert manifest is not None
        assert manifest.account_name == "opt_manifest_e2e"
        # Resolved from the real default universe file threaded into the run config.
        assert manifest.universe_size == 12
        assert '"AAPL"' in manifest.universe_tickers_json
        # The composition root binds the provider name; the default fake path records "unknown".
        assert manifest.market_data_provider == "unknown"
        assert manifest.manifest_version == "manifest_v1"


class TestPromotion:
    def test_promotes_winner_into_frozen_variant_and_links_back(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_e2e")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_e2e")

        variant = promote_optimization_experiment(conn, experiment_id=experiment_id, new_strategy_key="trend_wfo")

        assert variant.strategy_key == "trend_wfo"
        assert variant.primitive == "trend"
        assert variant.status == "frozen"  # frozen by default (evidence-backed)
        assert json.loads(variant.params_json) == WINNER
        assert variant.description is not None and f"experiment #{experiment_id}" in variant.description

        record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
        assert record is not None and record.promoted_strategy_id == variant.id

    def test_no_freeze_leaves_a_draft(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_draft")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_draft")

        variant = promote_optimization_experiment(
            conn, experiment_id=experiment_id, new_strategy_key="trend_wfo_draft", freeze=False
        )
        assert variant.status == "draft"

    def test_re_promotion_is_rejected(self, conn) -> None:
        account_id = insert_repository_account(conn, name="opt_twice")
        experiment_id = _run_and_persist(conn, account_id, account_name="opt_twice")
        promote_optimization_experiment(conn, experiment_id=experiment_id, new_strategy_key="trend_wfo_a")

        with pytest.raises(ValueError, match="already promoted"):
            promote_optimization_experiment(conn, experiment_id=experiment_id, new_strategy_key="trend_wfo_b")

    def test_unknown_experiment_raises_not_found(self, conn) -> None:
        with pytest.raises(NotFoundError, match="not found"):
            promote_optimization_experiment(conn, experiment_id=999, new_strategy_key="nope")

    def test_promotion_gate_is_operational_not_edge(self, conn) -> None:
        # An experiment whose winner UNDERPERFORMED the default (beat 0 windows,
        # holdout winner < baseline) is still promotable — the gate is operational
        # completeness, not out-of-sample edge.
        account_id = insert_repository_account(conn, name="opt_noedge")
        experiment_id = insert_experiment(
            conn,
            OptimizationExperimentInsert(
                account_id=account_id,
                strategy_id=None,
                primitive="trend",
                objective_name="calmar_v1",
                search_space_json='{"slow_window": [20, 40]}',
                candidate_budget=256,
                train_months=6,
                test_months=1,
                step_months=1,
                holdout_months=3,
                warmup_months=6,
                start_date="2022-01-01",
                end_date="2023-12-31",
                window_count=3,
                winner_params_json=json.dumps(WINNER),
                oos_mean_winner_return_pct=0.5,
                oos_mean_baseline_return_pct=1.5,
                oos_windows_beat_baseline=0,
                holdout_run_id=None,
                holdout_winner_return_pct=0.7,
                holdout_baseline_return_pct=4.0,
            ),
            created_at="2026-07-24T00:00:00Z",
        )

        variant = promote_optimization_experiment(
            conn, experiment_id=experiment_id, new_strategy_key="trend_underperformer"
        )
        assert variant.status == "frozen"
        assert json.loads(variant.params_json) == WINNER
