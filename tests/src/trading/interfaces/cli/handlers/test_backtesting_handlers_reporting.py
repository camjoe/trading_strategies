from __future__ import annotations

import types

import pytest

from backtesting.models.optimizer import ExperimentAudit, ExperimentWindowAudit
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser
from tests.support.backtesting import make_backtest_full_report
from trading.domain.promotion_gate import evaluate_promotion_gate
from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest_leaderboard,
    handle_backtest_optimize_show,
    handle_backtest_report,
)


def test_handle_backtest_report_prints_run_id(capsys) -> None:
    deps = {"fetch_report": lambda _conn, *, run_id: make_backtest_full_report(run_id=42, run_name="smoke")}

    handle_backtest_report(object(), types.SimpleNamespace(run_id=42), fake_parser(), deps=deps)

    out = capsys.readouterr().out
    assert "42" in out
    assert "Risk Analytics:" in out
    assert "Trade Analytics:" in out


def test_handle_backtest_report_joins_the_warning_list(capsys) -> None:
    """``summary.warnings`` is ``list[str]``; the line must read as prose, not a repr."""
    report = make_backtest_full_report(warnings=["daily bars only", "approximate leaps"])
    deps = {"fetch_report": lambda _conn, *, run_id: report}

    handle_backtest_report(object(), types.SimpleNamespace(run_id=1), fake_parser(), deps=deps)

    assert "Safeguards / notes: daily bars only | approximate leaps" in capsys.readouterr().out


def test_handle_backtest_leaderboard_prints_csv_header(capsys) -> None:
    row = types.SimpleNamespace(
        run_id=1,
        run_name="r",
        account_name="acct",
        strategy="trend",
        start_date="2026-01-01",
        end_date="2026-03-01",
        ending_equity=10500.0,
        total_return_pct=5.0,
        max_drawdown_pct=-2.0,
        benchmark_return_pct=3.0,
        alpha_pct=2.0,
        sharpe_ratio=1.1,
        sortino_ratio=1.4,
        calmar_ratio=0.7,
        win_rate_pct=55.0,
        profit_factor=1.5,
        avg_trade_return_pct=2.0,
        trade_count=3,
        created_at="2026-03-01",
    )
    deps = {"fetch_leaderboard": lambda *_a, **_kw: [row]}
    args = types.SimpleNamespace(limit=10, account=None, strategy=None)

    handle_backtest_leaderboard(object(), args, fake_parser(), deps=deps)

    out = capsys.readouterr().out
    assert "run_id" in out
    assert "sharpe_ratio" in out


def test_handle_backtest_leaderboard_prints_no_results_when_empty(capsys) -> None:
    deps = {"fetch_leaderboard": lambda *_a, **_kw: []}
    args = types.SimpleNamespace(limit=10, account=None, strategy=None)

    handle_backtest_leaderboard(object(), args, fake_parser(), deps=deps)

    assert "No backtest runs" in capsys.readouterr().out


def test_handle_backtest_leaderboard_routes_value_error_to_parser_error() -> None:
    deps = {
        "fetch_leaderboard": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        )
    }
    args = types.SimpleNamespace(limit=10, account=None, strategy="mystery_strategy")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_leaderboard(object(), args, fake_parser(), deps=deps)


class _RecordingParser:
    def __init__(self) -> None:
        self.message: str | None = None

    def error(self, msg: str) -> None:
        self.message = msg


def test_handle_backtest_leaderboard_records_parser_error_without_printing_header(capsys) -> None:
    parser = _RecordingParser()
    deps = {
        "fetch_leaderboard": lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad leaderboard")),
    }
    args = types.SimpleNamespace(limit=10, account=None, strategy="mystery_strategy")

    handle_backtest_leaderboard(object(), args, parser, deps=deps)

    assert parser.message == "bad leaderboard"
    assert "run_id,run_name" not in capsys.readouterr().out


def _experiment_stub(*, status="completed", failure_stage=None, failure_message=None):
    return types.SimpleNamespace(
        id=5,
        account_id=1,
        primitive="trend",
        objective_name="calmar_v1",
        created_at="2026-07-25T00:00:00Z",
        start_date="2022-01-01",
        end_date="2023-12-31",
        window_count=1,
        train_months=6,
        test_months=1,
        step_months=1,
        holdout_months=3,
        warmup_months=6,
        search_space_json='{"slow_window": [20, 40]}',
        candidate_budget=256,
        winner_params_json='{"slow_window": 40}',
        oos_mean_winner_return_pct=None,
        oos_mean_baseline_return_pct=None,
        oos_windows_beat_baseline=None,
        holdout_run_id=None,
        holdout_winner_return_pct=None,
        holdout_baseline_return_pct=None,
        promoted_strategy_id=None,
        status=status,
        failure_stage=failure_stage,
        failure_message=failure_message,
    )


def _manifest_stub():
    return types.SimpleNamespace(
        manifest_version="manifest_v1",
        account_name="acct",
        book_id=3,
        initial_cash=25_000.0,
        benchmark_ticker="SPY",
        slippage_bps=5.0,
        fee_per_trade=0.0,
        effective_execution_json='{"risk_policy": "none"}',
        tickers_file="universe.txt",
        universe_history_dir=None,
        universe_size=12,
        market_data_provider="yfinance",
        data_as_of="2026-07-25T00:00:00Z",
        engine_revision="abc123",
    )


def test_handle_backtest_optimize_show_prints_per_window_audit(capsys) -> None:
    window = types.SimpleNamespace(
        id=11,
        window_index=1,
        train_start="2022-01-01",
        train_end="2022-06-30",
        test_start="2022-07-01",
        test_end="2022-07-31",
        oos_run_id=101,
    )
    trials = [
        types.SimpleNamespace(
            window_id=11,
            candidate_index=0,
            eligible=True,
            selected=True,
            objective_value=1.5,
            rejection_reason=None,
        ),
        types.SimpleNamespace(
            window_id=11,
            candidate_index=1,
            eligible=False,
            selected=False,
            objective_value=None,
            rejection_reason="too_few_trades (1 < 3)",
        ),
    ]
    series = types.SimpleNamespace(
        points=[
            types.SimpleNamespace(
                window_index=1,
                test_start="2022-07-01",
                test_end="2022-07-31",
                period_return_pct=2.0,
                cumulative_return_pct=2.0,
                gap_before=False,
            ),
            types.SimpleNamespace(
                window_index=2,
                test_start="2022-09-01",
                test_end="2022-09-30",
                period_return_pct=3.0,
                cumulative_return_pct=5.06,
                gap_before=True,
            ),
        ],
        compounded_return_pct=5.06,
        has_gaps=True,
    )
    audit = ExperimentAudit(
        experiment=_experiment_stub(),
        windows=[ExperimentWindowAudit(window=window, trials=trials)],
        compounded_oos=series,
        manifest=_manifest_stub(),
    )
    deps = {
        "fetch_experiment_audit": lambda _conn, *, experiment_id: audit,
        "evaluate_promotion_gate": evaluate_promotion_gate,
    }

    handle_backtest_optimize_show(object(), types.SimpleNamespace(experiment_id=5), fake_parser(), deps=deps)

    out = capsys.readouterr().out
    assert "Windows (1) with per-candidate trials:" in out
    assert "W01 train 2022-01-01..2022-06-30 test 2022-07-01..2022-07-31 (oos run 101)" in out
    assert "2 candidates, 1 eligible | win #0" in out
    assert "rejected: too_few_trades x1" in out
    assert "Compounded OOS (across 2 windows, 1 gap(s)): 5.06%" in out
    assert "W02 2022-09-01..2022-09-30 [GAP] period 3.00% | cumulative 5.06%" in out
    assert "Provenance (manifest_v1) | account=acct book_id=3" in out
    assert "universe: 12 tickers | lineage=universe.txt" in out
    assert "provider=yfinance" in out


def test_handle_backtest_optimize_show_notes_when_no_windows_persisted(capsys) -> None:
    audit = ExperimentAudit(experiment=_experiment_stub(), windows=[], compounded_oos=None, manifest=None)
    deps = {
        "fetch_experiment_audit": lambda _conn, *, experiment_id: audit,
        "evaluate_promotion_gate": evaluate_promotion_gate,
    }

    handle_backtest_optimize_show(object(), types.SimpleNamespace(experiment_id=5), fake_parser(), deps=deps)

    out = capsys.readouterr().out
    assert "Windows: none persisted" in out
    assert "Compounded OOS: unavailable" in out
    assert "Provenance: unavailable" in out


def test_handle_backtest_optimize_show_prints_failure_and_skips_the_audit_sections(capsys) -> None:
    # A failed experiment never persisted an audit tree, so the service hands back
    # empty windows and no series/manifest; the handler must stop after the header
    # rather than print "none persisted" lines that read like data loss.
    audit = ExperimentAudit(
        experiment=_experiment_stub(
            status="failed", failure_stage="window_search", failure_message="No eligible candidate: too_few_trades"
        ),
        windows=[],
        compounded_oos=None,
        manifest=None,
    )
    deps = {
        "fetch_experiment_audit": lambda _conn, *, experiment_id: audit,
        "evaluate_promotion_gate": evaluate_promotion_gate,
    }

    handle_backtest_optimize_show(object(), types.SimpleNamespace(experiment_id=5), fake_parser(), deps=deps)

    out = capsys.readouterr().out
    assert "status=failed" in out
    assert "Failed during window_search after 1 window(s): No eligible candidate: too_few_trades" in out
    assert "Windows" not in out
    assert "Compounded OOS" not in out
    assert "Provenance" not in out


def test_handle_backtest_optimize_show_errors_on_missing_experiment() -> None:
    deps = {"fetch_experiment_audit": lambda _conn, *, experiment_id: None}

    with pytest.raises(SystemExit, match="Optimization experiment not found: 5"):
        handle_backtest_optimize_show(object(), types.SimpleNamespace(experiment_id=5), fake_parser(), deps=deps)
