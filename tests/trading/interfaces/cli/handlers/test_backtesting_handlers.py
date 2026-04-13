from __future__ import annotations

import types

import pytest

from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest,
    handle_backtest_batch,
    handle_backtest_leaderboard,
    handle_backtest_report,
    handle_backtest_walk_forward,
)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def _backtest_args(**kwargs) -> types.SimpleNamespace:
    defaults = dict(
        account="acct",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name=None,
        allow_approximate_leaps=False,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _fake_result(**kwargs) -> types.SimpleNamespace:
    defaults = dict(
        run_id=1,
        account_name="acct",
        start_date="2026-01-01",
        end_date="2026-03-01",
        trade_count=5,
        ending_equity=10500.0,
        total_return_pct=5.0,
        max_drawdown_pct=-2.0,
        benchmark_return_pct=3.0,
        alpha_pct=2.0,
        sharpe_ratio=None,
        sortino_ratio=None,
        calmar_ratio=None,
        win_rate_pct=None,
        profit_factor=None,
        avg_trade_return_pct=None,
        warnings=[],
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_handle_backtest_calls_run_backtest_with_built_config() -> None:
    configs: list = []
    deps = {
        "BacktestConfig": lambda **kw: configs.append(kw) or types.SimpleNamespace(**kw),
        "run_backtest": lambda _conn, _cfg: _fake_result(),
    }

    handle_backtest(object(), _backtest_args(account="my_acct"), _parser(), deps=deps, module_file="", db_path="")

    assert len(configs) == 1
    assert configs[0]["account_name"] == "my_acct"
    assert configs[0]["slippage_bps"] == 5.0


def test_handle_backtest_prints_warnings_when_present(capsys) -> None:
    result = _fake_result(warnings=["LEAPs mode is approximated"])
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: result,
    }

    handle_backtest(object(), _backtest_args(), _parser(), deps=deps, module_file="", db_path="")

    assert "LEAPs mode is approximated" in capsys.readouterr().out


def test_handle_backtest_routes_value_error_to_parser_error() -> None:
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery_strategy'")),
    }

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest(object(), _backtest_args(), _parser(), deps=deps, module_file="", db_path="")


def test_handle_backtest_omits_benchmark_line_when_unavailable(capsys) -> None:
    result = _fake_result(benchmark_return_pct=None, alpha_pct=None)
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: result,
    }

    handle_backtest(object(), _backtest_args(), _parser(), deps=deps, module_file="", db_path="")

    out = capsys.readouterr().out
    assert "Benchmark comparison unavailable" in out
    assert "Risk Analytics:" in out
    assert "Trade Analytics:" in out


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


def test_handle_backtest_batch_prints_rank_table(capsys) -> None:
    deps = {
        "BacktestBatchConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest_batch": lambda _conn, _cfg: [_fake_result()],
    }
    args = types.SimpleNamespace(
        accounts="acct_a, acct_b",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix=None,
        allow_approximate_leaps=False,
    )

    handle_backtest_batch(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert "rank" in capsys.readouterr().out


def test_handle_backtest_batch_splits_accounts_on_comma() -> None:
    seen_accounts: list = []

    def _fake_batch(_conn, cfg):
        seen_accounts.extend(cfg.account_names)
        return []

    deps = {
        "BacktestBatchConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest_batch": _fake_batch,
    }
    args = types.SimpleNamespace(
        accounts=" acct_a , acct_b ",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix=None,
        allow_approximate_leaps=False,
    )

    handle_backtest_batch(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert seen_accounts == ["acct_a", "acct_b"]


def test_handle_backtest_batch_routes_value_error_to_parser_error() -> None:
    deps = {
        "BacktestBatchConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest_batch": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = types.SimpleNamespace(
        accounts="acct_a",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-01",
        lookback_months=None,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix=None,
        allow_approximate_leaps=False,
    )

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_batch(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_backtest_walk_forward_prints_window_count(capsys) -> None:
    summary = types.SimpleNamespace(
        account_name="acct",
        start_date="2026-01-01",
        end_date="2026-03-31",
        window_count=3,
        average_return_pct=4.0,
        median_return_pct=3.5,
        best_return_pct=6.0,
        worst_return_pct=2.0,
        run_ids=[1, 2, 3],
    )
    deps = {
        "WalkForwardConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_walk_forward_backtest": lambda _conn, _cfg: summary,
    }
    args = types.SimpleNamespace(
        account="acct",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-31",
        lookback_months=None,
        test_months=1,
        step_months=1,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix=None,
        allow_approximate_leaps=False,
    )

    handle_backtest_walk_forward(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert "windows=3" in capsys.readouterr().out


def test_handle_backtest_walk_forward_routes_value_error_to_parser_error() -> None:
    deps = {
        "WalkForwardConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_walk_forward_backtest": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = types.SimpleNamespace(
        account="acct",
        tickers_file="tickers.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-03-31",
        lookback_months=None,
        test_months=1,
        step_months=1,
        slippage_bps=5.0,
        fee=0.0,
        run_name_prefix=None,
        allow_approximate_leaps=False,
    )

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_walk_forward(object(), args, _parser(), deps=deps, module_file="", db_path="")
