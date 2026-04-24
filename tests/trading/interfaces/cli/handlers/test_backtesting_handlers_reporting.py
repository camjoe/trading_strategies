from __future__ import annotations

import types

import pytest

from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest_leaderboard,
    handle_backtest_report,
    handle_backtest_walk_forward_report,
)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def test_handle_backtest_report_prints_run_id(capsys) -> None:
    report = {
        "run_id": 42,
        "run_name": "smoke",
        "account_name": "acct",
        "strategy": "trend",
        "start_date": "2026-01-01",
        "end_date": "2026-03-01",
        "created_at": "2026-03-01",
        "trade_count": 3,
        "starting_equity": 10000.0,
        "ending_equity": 10500.0,
        "total_return_pct": 5.0,
        "max_drawdown_pct": -2.0,
        "slippage_bps": 5.0,
        "fee_per_trade": 0.0,
        "tickers_file": "tickers.txt",
        "warnings": "",
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.5,
        "calmar_ratio": 0.8,
        "win_rate_pct": 60.0,
        "profit_factor": 1.7,
        "avg_trade_return_pct": 2.5,
    }
    deps = {"backtest_report": lambda _conn, _run_id: report}

    handle_backtest_report(
        object(), types.SimpleNamespace(run_id=42), _parser(), deps=deps, module_file="", db_path=""
    )

    out = capsys.readouterr().out
    assert "42" in out
    assert "Risk Analytics:" in out
    assert "Trade Analytics:" in out


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
    deps = {"backtest_leaderboard_entries": lambda *_a, **_kw: [row]}
    args = types.SimpleNamespace(limit=10, account=None, strategy=None)

    handle_backtest_leaderboard(object(), args, _parser(), deps=deps, module_file="", db_path="")

    out = capsys.readouterr().out
    assert "run_id" in out
    assert "sharpe_ratio" in out


def test_handle_backtest_leaderboard_prints_no_results_when_empty(capsys) -> None:
    deps = {"backtest_leaderboard_entries": lambda *_a, **_kw: []}
    args = types.SimpleNamespace(limit=10, account=None, strategy=None)

    handle_backtest_leaderboard(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert "No backtest runs" in capsys.readouterr().out


def test_handle_backtest_leaderboard_routes_value_error_to_parser_error() -> None:
    deps = {
        "backtest_leaderboard_entries": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        )
    }
    args = types.SimpleNamespace(limit=10, account=None, strategy="mystery_strategy")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_leaderboard(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_backtest_walk_forward_report_prints_window_rows(capsys) -> None:
    report = {
        "group_id": 7,
        "account_name": "acct",
        "strategy_name": "trend",
        "run_name_prefix": "wf",
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "created_at": "2026-04-14T00:00:00Z",
        "window_count": 2,
        "average_return_pct": 4.0,
        "median_return_pct": 4.0,
        "best_return_pct": 5.0,
        "worst_return_pct": 3.0,
        "windows": [
            {
                "window_index": 1,
                "window_start": "2026-01-01",
                "window_end": "2026-01-31",
                "total_return_pct": 3.0,
                "backtest_summary": {
                    "run_id": 101,
                    "run_name": "wf_01",
                    "max_drawdown_pct": -1.0,
                    "trade_count": 5,
                },
            }
        ],
    }
    deps = {"walk_forward_report": lambda *_a, **_kw: report}
    args = types.SimpleNamespace(group_id=7, account=None, strategy=None)

    handle_backtest_walk_forward_report(object(), args, _parser(), deps=deps, module_file="", db_path="")

    out = capsys.readouterr().out
    assert "Walk-forward Group 7" in out
    assert "window,range,run_id,run_name,return_pct,max_drawdown_pct,trade_count" in out
    assert "101,wf_01" in out


def test_handle_backtest_walk_forward_report_routes_value_error_to_parser_error() -> None:
    deps = {
        "walk_forward_report": lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("Walk-forward group 7 not found."))
    }
    args = types.SimpleNamespace(group_id=7, account=None, strategy=None)

    with pytest.raises(SystemExit, match="Walk-forward group 7 not found."):
        handle_backtest_walk_forward_report(object(), args, _parser(), deps=deps, module_file="", db_path="")
