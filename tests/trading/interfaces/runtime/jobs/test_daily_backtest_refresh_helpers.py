from pathlib import Path

from tests.support import daily_backtest_refresh as module, make_daily_backtest_refresh_args


def test_already_completed_today_detects_sentinel(tmp_path: Path) -> None:
    day_tag = "20260414"
    log = tmp_path / f"daily_backtest_refresh_{day_tag}_010101.log"
    log.write_text(f"anything\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

    assert module.already_completed_today(tmp_path, day_tag) is True


def test_retry_delay_seconds_doubles_each_attempt() -> None:
    assert module.retry_delay_seconds(2.0, 1) == 2.0
    assert module.retry_delay_seconds(2.0, 2) == 4.0
    assert module.retry_delay_seconds(2.0, 3) == 8.0


def test_build_backtest_command_includes_optional_settings() -> None:
    command = module.build_backtest_command(
        account="acct1",
        args=make_daily_backtest_refresh_args(
            tickers_file="local/tickers.txt",
            universe_history_dir="local/history",
            start="2025-01-01",
            end="2025-12-31",
            lookback_months=None,
            allow_approximate_leaps=True,
            fee=1.25,
        ),
        day_tag="20260414",
    )

    assert command[:5] == ["-m", "trading.interfaces.cli.main", "backtest", "--account", "acct1"]
    assert "--universe-history-dir" in command
    assert "--start" in command
    assert "--end" in command
    assert "--allow-approximate-leaps" in command


def test_extract_run_id_returns_integer_when_present() -> None:
    assert module.extract_run_id("Backtest complete: run_id=42 account=acct") == 42


def test_extract_run_id_returns_none_when_absent() -> None:
    assert module.extract_run_id("Backtest completed without summary") is None
