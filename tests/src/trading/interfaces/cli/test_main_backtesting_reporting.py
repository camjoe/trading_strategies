from __future__ import annotations

from tests.src.trading.interfaces.cli.factories import make_backtest_leaderboard_args, make_backtest_report_args
from tests.src.trading.interfaces.cli.helpers import install_main_harness
from tests.support.backtesting import make_backtest_full_report, make_backtest_leaderboard_entry
from trading.interfaces.cli import main as cli_main


def test_main_backtest_report_dispatches(monkeypatch, capsys) -> None:
    args = make_backtest_report_args(run_id=11)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(
        cli_main,
        "backtest_report_full",
        lambda _conn, run_id: make_backtest_full_report(
            run_id=run_id,
            run_name="wf-1",
            warnings=["daily bars only"],
        ),
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest Run 11 (wf-1)" in out
    assert "Safeguards / notes: daily bars only" in out
    assert fake_conn.closed is True


def test_main_backtest_report_without_warnings_omits_notes_line(monkeypatch, capsys) -> None:
    args = make_backtest_report_args(run_id=99)
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(
        cli_main,
        "backtest_report_full",
        lambda _conn, run_id: make_backtest_full_report(run_id=run_id, run_name=None, warnings=[]),
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "Backtest Run 99 (unnamed)" in out
    assert "Safeguards / notes:" not in out
    assert fake_conn.closed is True


def test_main_backtest_leaderboard_dispatches(monkeypatch, capsys) -> None:
    args = make_backtest_leaderboard_args(limit=5, strategy="trend")
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(
        cli_main,
        "backtest_leaderboard_entries",
        lambda _conn, *, limit, account_name, strategy: [
            make_backtest_leaderboard_entry(
                "acct1",
                run_id=9,
                run_name="batch_01",
                total_return_pct=5.0,
                ending_equity=10_500.0,
                trade_count=8,
                max_drawdown_pct=-1.2,
                benchmark_return_pct=2.0,
                alpha_pct=3.0,
            )
        ],
    )

    cli_main.main()

    out = capsys.readouterr().out
    assert "run_id,run_name,account_name,strategy" in out
    assert "9,batch_01,acct1,trend_v1" in out
    assert fake_conn.closed is True


def test_main_backtest_leaderboard_no_rows_prints_message(monkeypatch, capsys) -> None:
    args = make_backtest_leaderboard_args()
    fake_conn = install_main_harness(monkeypatch, cli_main, args)
    monkeypatch.setattr(cli_main, "backtest_leaderboard_entries", lambda *_args, **_kwargs: [])

    cli_main.main()

    out = capsys.readouterr().out
    assert "No backtest runs matched the selected filters." in out
    assert fake_conn.closed is True
