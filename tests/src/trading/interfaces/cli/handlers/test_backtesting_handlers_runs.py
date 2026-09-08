from __future__ import annotations

import types

import pytest

import trading.interfaces.cli.handlers.backtesting_handlers as module
from tests.src.trading.interfaces.cli.factories import (
    make_backtest_args,
    make_backtest_batch_args,
    make_backtest_result,
)
from tests.src.trading.interfaces.cli.handlers.helpers import fake_parser, make_ctx, patch_services
from trading.interfaces.cli.handlers.backtesting_handlers import (
    handle_backtest,
    handle_backtest_batch,
)


def test_handle_backtest_calls_run_backtest_with_built_config(monkeypatch) -> None:
    configs: list = []
    patch_services(
        monkeypatch,
        module,
        BacktestConfig=lambda **kw: configs.append(kw) or types.SimpleNamespace(**kw),
        run_backtest=lambda _conn, _cfg, **_kw: make_backtest_result(account_name="acct"),
    )

    handle_backtest(object(), make_backtest_args(account="my_acct"), fake_parser(), ctx=make_ctx())

    assert len(configs) == 1
    assert configs[0]["account_name"] == "my_acct"
    assert configs[0]["slippage_bps"] == 5.0


def test_handle_backtest_prints_warnings_when_present(capsys, monkeypatch) -> None:
    result = make_backtest_result(account_name="acct", warnings=["LEAPs mode is approximated"])
    patch_services(
        monkeypatch,
        module,
        BacktestConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest=lambda *_a, **_kw: result,
    )

    handle_backtest(object(), make_backtest_args(), fake_parser(), ctx=make_ctx())

    assert "LEAPs mode is approximated" in capsys.readouterr().out


def test_handle_backtest_routes_value_error_to_parser_error(monkeypatch) -> None:
    patch_services(
        monkeypatch,
        module,
        BacktestConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery_strategy'")),
    )

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest(object(), make_backtest_args(), fake_parser(), ctx=make_ctx())


def test_handle_backtest_omits_benchmark_line_when_unavailable(capsys, monkeypatch) -> None:
    result = make_backtest_result(account_name="acct", benchmark_return_pct=None, alpha_pct=None)
    patch_services(
        monkeypatch,
        module,
        BacktestConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest=lambda *_a, **_kw: result,
    )

    handle_backtest(object(), make_backtest_args(), fake_parser(), ctx=make_ctx())

    out = capsys.readouterr().out
    assert "Benchmark comparison unavailable" in out
    assert "Risk Analytics:" in out
    assert "Trade Analytics:" in out


def test_handle_backtest_batch_prints_rank_table(capsys, monkeypatch) -> None:
    patch_services(
        monkeypatch,
        module,
        BacktestBatchConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest_batch=lambda _conn, _cfg, **_kw: [make_backtest_result(account_name="acct")],
    )
    args = make_backtest_batch_args(
        accounts="acct_a, acct_b",
        tickers_file="tickers.txt",
    )

    handle_backtest_batch(object(), args, fake_parser(), ctx=make_ctx())

    assert "rank" in capsys.readouterr().out


def test_handle_backtest_batch_splits_accounts_on_comma(monkeypatch) -> None:
    seen_accounts: list = []

    def _fake_batch(_conn, cfg, **_kw):
        seen_accounts.extend(cfg.account_names)
        return []

    patch_services(
        monkeypatch,
        module,
        BacktestBatchConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest_batch=_fake_batch,
    )
    args = make_backtest_batch_args(accounts=" acct_a , acct_b ", tickers_file="tickers.txt")

    handle_backtest_batch(object(), args, fake_parser(), ctx=make_ctx())

    assert seen_accounts == ["acct_a", "acct_b"]


def test_handle_backtest_batch_routes_value_error_to_parser_error(monkeypatch) -> None:
    patch_services(
        monkeypatch,
        module,
        BacktestBatchConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest_batch=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("Unknown strategy 'mystery_strategy'")),
    )
    args = make_backtest_batch_args(accounts="acct_a", tickers_file="tickers.txt")

    with pytest.raises(SystemExit, match="Unknown strategy 'mystery_strategy'"):
        handle_backtest_batch(object(), args, fake_parser(), ctx=make_ctx())


class _RecordingParser:
    def __init__(self) -> None:
        self.message: str | None = None

    def error(self, msg: str) -> None:
        self.message = msg


def test_handle_backtest_records_parser_error_without_printing_success(capsys, monkeypatch) -> None:
    parser = _RecordingParser()
    patch_services(
        monkeypatch,
        module,
        BacktestConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad backtest")),
    )

    handle_backtest(object(), make_backtest_args(), parser, ctx=make_ctx())

    assert parser.message == "bad backtest"
    assert "Backtest complete" not in capsys.readouterr().out


def test_handle_backtest_batch_records_parser_error_without_printing_success(capsys, monkeypatch) -> None:
    parser = _RecordingParser()
    patch_services(
        monkeypatch,
        module,
        BacktestBatchConfig=lambda **kw: types.SimpleNamespace(**kw),
        run_backtest_batch=lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("bad batch")),
    )

    handle_backtest_batch(
        object(),
        make_backtest_batch_args(accounts="acct_a", tickers_file="tickers.txt"),
        parser,
        ctx=make_ctx(),
    )

    assert parser.message == "bad batch"
    assert "Backtest batch complete" not in capsys.readouterr().out
