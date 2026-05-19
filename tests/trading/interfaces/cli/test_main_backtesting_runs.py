from __future__ import annotations

from tests.support.cli.backtesting import (
    make_backtest_args,
    make_backtest_batch_args,
    make_backtest_result,
    make_walk_forward_args,
    make_walk_forward_summary,
)
from tests.support.cli.main import install_main_harness
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
        cli_main,
        "run_backtest",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or result,
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
    monkeypatch.setattr(cli_main, "run_backtest", lambda _conn, _cfg: result)

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest complete: run_id=8" in out
    assert "Benchmark comparison unavailable for selected date range." in out
    assert "Backtest safeguards / approximation notes:" not in out
    assert fake_conn.closed is True


def test_main_backtest_walk_forward_dispatches(monkeypatch, capsys) -> None:
    args = make_walk_forward_args(account="acct1", run_name_prefix="wf")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    summary = make_walk_forward_summary(run_ids=[101, 102, 103])
    monkeypatch.setattr(
        cli_main,
        "run_walk_forward_backtest",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or summary,
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].test_months == 1
    out = capsys.readouterr().out
    assert "Walk-forward complete: account=acct1" in out
    assert "Generated run ids: 101, 102, 103" in out
    assert fake_conn.closed is True


def test_main_backtest_walk_forward_prints_run_id_ellipsis(monkeypatch, capsys) -> None:
    args = make_walk_forward_args(account="acct1", run_name_prefix="wf")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    summary = make_walk_forward_summary(window_count=12, run_ids=list(range(101, 113)))
    monkeypatch.setattr(cli_main, "run_walk_forward_backtest", lambda _conn, _cfg: summary)

    cli_main.main()

    out = capsys.readouterr().out
    assert "Generated run ids: 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, ..." in out
    assert fake_conn.closed is True


def test_main_backtest_batch_dispatches(monkeypatch, capsys) -> None:
    args = make_backtest_batch_args(accounts="acct1, acct2", run_name_prefix="batch")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    captured = {}
    result_a = make_backtest_result(account_name="acct2", run_id=22, total_return_pct=3.0, max_drawdown_pct=-1.0)
    result_b = make_backtest_result(account_name="acct1", run_id=21, total_return_pct=1.0, max_drawdown_pct=-1.0)
    monkeypatch.setattr(
        cli_main,
        "run_backtest_batch",
        lambda conn, cfg: captured.update({"conn": conn, "cfg": cfg}) or [result_a, result_b],
    )

    cli_main.main()

    assert captured["conn"] is fake_conn
    assert captured["cfg"].account_names == ["acct1", "acct2"]
    out = capsys.readouterr().out
    assert "Backtest batch complete." in out
    assert "1,acct2,22,3.0000" in out
    assert fake_conn.closed is True
