from __future__ import annotations

import types

import pytest

from tests.support.cli.backtesting import (
    make_backtest_args,
    make_backtest_batch_args,
    make_backtest_result,
    make_walk_forward_args,
    make_walk_forward_summary,
)
from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest,
    handle_backtest_batch,
    handle_backtest_walk_forward,
)


def _parser():
    class _P:
        def error(self, msg: str) -> None:
            raise SystemExit(msg)

    return _P()


def test_handle_backtest_calls_run_backtest_with_built_config() -> None:
    configs: list = []
    deps = {
        "BacktestConfig": lambda **kw: configs.append(kw) or types.SimpleNamespace(**kw),
        "run_backtest": lambda _conn, _cfg: make_backtest_result(account_name="acct"),
    }

    handle_backtest(object(), make_backtest_args(account="my_acct"), _parser(), deps=deps, module_file="", db_path="")

    assert len(configs) == 1
    assert configs[0]["account_name"] == "my_acct"
    assert configs[0]["slippage_bps"] == 5.0


def test_handle_backtest_prints_warnings_when_present(capsys) -> None:
    result = make_backtest_result(account_name="acct", warnings=["LEAPs mode is approximated"])
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: result,
    }

    handle_backtest(object(), make_backtest_args(), _parser(), deps=deps, module_file="", db_path="")

    assert "LEAPs mode is approximated" in capsys.readouterr().out


def test_handle_backtest_routes_value_error_to_parser_error() -> None:
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery_strategy'")),
    }

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest(object(), make_backtest_args(), _parser(), deps=deps, module_file="", db_path="")


def test_handle_backtest_omits_benchmark_line_when_unavailable(capsys) -> None:
    result = make_backtest_result(account_name="acct", benchmark_return_pct=None, alpha_pct=None)
    deps = {
        "BacktestConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest": lambda *_: result,
    }

    handle_backtest(object(), make_backtest_args(), _parser(), deps=deps, module_file="", db_path="")

    out = capsys.readouterr().out
    assert "Benchmark comparison unavailable" in out
    assert "Risk Analytics:" in out
    assert "Trade Analytics:" in out


def test_handle_backtest_batch_prints_rank_table(capsys) -> None:
    deps = {
        "BacktestBatchConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest_batch": lambda _conn, _cfg: [make_backtest_result(account_name="acct")],
    }
    args = make_backtest_batch_args(
        accounts="acct_a, acct_b",
        tickers_file="tickers.txt",
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
    args = make_backtest_batch_args(accounts=" acct_a , acct_b ", tickers_file="tickers.txt")

    handle_backtest_batch(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert seen_accounts == ["acct_a", "acct_b"]


def test_handle_backtest_batch_routes_value_error_to_parser_error() -> None:
    deps = {
        "BacktestBatchConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_backtest_batch": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = make_backtest_batch_args(accounts="acct_a", tickers_file="tickers.txt")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_batch(object(), args, _parser(), deps=deps, module_file="", db_path="")


def test_handle_backtest_walk_forward_prints_window_count(capsys) -> None:
    summary = make_walk_forward_summary(
        account_name="acct",
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
    args = make_walk_forward_args(account="acct", tickers_file="tickers.txt")

    handle_backtest_walk_forward(object(), args, _parser(), deps=deps, module_file="", db_path="")

    assert "windows=3" in capsys.readouterr().out


def test_handle_backtest_walk_forward_routes_value_error_to_parser_error() -> None:
    deps = {
        "WalkForwardConfig": lambda **kw: types.SimpleNamespace(**kw),
        "run_walk_forward_backtest": lambda *_a, **_kw: (_ for _ in ()).throw(
            ValueError("Unknown strategy 'mystery_strategy'")
        ),
    }
    args = make_walk_forward_args(account="acct", tickers_file="tickers.txt")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_walk_forward(object(), args, _parser(), deps=deps, module_file="", db_path="")
