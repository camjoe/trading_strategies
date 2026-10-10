from __future__ import annotations

import trading.interfaces.cli.handlers.backtesting_handlers as backtesting_handlers
from tests.src.trading.interfaces.cli.factories import (
    make_backtest_args,
    make_backtest_batch_args,
    make_backtest_result,
)
from tests.src.trading.interfaces.cli.helpers import install_main_harness
from trading.interfaces.cli import main as cli_main


def test_main_backtest_dispatches_and_prints_summary(monkeypatch, capsys) -> None:
    args = make_backtest_args(account="acct1", run_name="smoke")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    result = make_backtest_result(
        run_id=7,
        account_name="acct1",
        ending_equity=10450.0,
        total_return_pct=4.5,
        benchmark_return_pct=3.0,
        alpha_pct=1.5,
        warnings=["daily bars only"],
    )
    monkeypatch.setattr(
        backtesting_handlers,
        "run_backtest",
        lambda conn, cfg, *, provider: captured.update({"conn": conn, "cfg": cfg}) or result,
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_name == "acct1"
    out = capsys.readouterr().out
    assert "Backtest complete: run_id=7" in out
    assert "Benchmark Return: 3.00% | Alpha: 1.50%" in out
    assert "Backtest safeguards / approximation notes:" in out
    assert fake_conn.closed is True


def test_main_backtest_without_benchmark_prints_unavailable(monkeypatch, capsys) -> None:
    args = make_backtest_args(account="acct1")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    result = make_backtest_result(
        run_id=8,
        account_name="acct1",
        trade_count=3,
        ending_equity=10300.0,
        total_return_pct=3.0,
        max_drawdown_pct=-1.0,
        benchmark_return_pct=None,
        alpha_pct=None,
        warnings=[],
    )
    monkeypatch.setattr(backtesting_handlers, "run_backtest", lambda _conn, _cfg, *, provider: result)

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest complete: run_id=8" in out
    assert "Benchmark comparison unavailable for selected date range." in out
    assert "Backtest safeguards / approximation notes:" not in out
    assert fake_conn.closed is True


def test_main_backtest_batch_dispatches(monkeypatch, capsys) -> None:
    args = make_backtest_batch_args(accounts="acct1, acct2", run_name_prefix="batch")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    result_a = make_backtest_result(account_name="acct2", run_id=22, total_return_pct=3.0, max_drawdown_pct=-1.0)
    result_b = make_backtest_result(account_name="acct1", run_id=21, total_return_pct=1.0, max_drawdown_pct=-1.0)
    monkeypatch.setattr(
        backtesting_handlers,
        "run_backtest_batch",
        lambda conn, cfg, *, provider: captured.update({"conn": conn, "cfg": cfg}) or [result_a, result_b],
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_names == ["acct1", "acct2"]
    out = capsys.readouterr().out
    assert "Backtest batch complete." in out
    assert "1,acct2,22,3.0000" in out
    assert fake_conn.closed is True
