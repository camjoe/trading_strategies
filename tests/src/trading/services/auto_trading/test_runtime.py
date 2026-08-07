from unittest.mock import Mock

import trading.services.auto_trading.runtime as runtime_service
from tests.src.trading.services.auto_trading.factories import (
    MARKET_CLOSED_TIME_ISO,
    make_auto_trading_account,
    make_feature_fetchers,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import run_for_account
from trading.models.execution import AccountRunResult


def test_run_for_account_skips_when_market_closed(monkeypatch) -> None:
    monkeypatch.setattr(runtime_service, "utc_now_iso", Mock(return_value=MARKET_CLOSED_TIME_ISO))
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda _now: False)
    broker_factory = Mock()
    books_runner = Mock()
    monkeypatch.setattr(runtime_service, "_run_books_for_account", books_runner)

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        max_trades=1,
        fee=0.0,
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 0
    broker_factory.assert_not_called()
    books_runner.assert_not_called()
    # Distinguishable from a quiet day, and not a kill switch: a shut market is
    # normal, and kill-switch reasons raise a warn alert.
    assert executed.submission_window_closed is True
    assert executed.halted is False


def test_run_for_account_delegates_to_book_path(monkeypatch) -> None:
    # The one execution path (ADR 014): market-window gate, then the book run.
    account = make_auto_trading_account(id=42)
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda _now: True)
    monkeypatch.setattr(runtime_service, "get_account", Mock(return_value=account))
    books_runner = Mock(return_value=AccountRunResult(account_name="acct", submitted_count=3))
    monkeypatch.setattr(runtime_service, "_run_books_for_account", books_runner)
    broker_factory = Mock()

    executed = run_for_account(
        conn=object(),
        account_name="acct",
        universe=["AAPL"],
        prices={"AAPL": 101.0},
        iv_rank_proxy={},
        max_trades=3,
        fee=0.0,
        broker_factory=broker_factory,
        feature_fetchers=make_feature_fetchers(),
    )

    assert executed.submitted_count == 3
    assert books_runner.call_count == 1
    assert books_runner.call_args.kwargs["account"] is account
    # The book path owns the broker lifecycle; the delegator opens nothing.
    broker_factory.assert_not_called()


def test_is_runtime_submission_window_open_parses_iso_before_market_hours_check(monkeypatch) -> None:
    parse_iso = Mock(return_value="parsed-dt")
    market_open = Mock(return_value=True)
    monkeypatch.setattr(runtime_service, "parse_utc_iso", parse_iso)
    monkeypatch.setattr(runtime_service, "is_regular_us_equity_market_open", market_open)

    assert runtime_service.is_runtime_submission_window_open("2026-03-14T14:00:00Z") is True
    parse_iso.assert_called_once_with("2026-03-14T14:00:00Z")
    market_open.assert_called_once_with("parsed-dt")


def test_is_runtime_submission_window_open_defaults_to_now(monkeypatch) -> None:
    # Callers that only want "is the market open right now" pass no argument.
    monkeypatch.setattr(runtime_service, "utc_now_iso", Mock(return_value="2026-03-14T14:00:00Z"))
    parse_iso = Mock(return_value="parsed-dt")
    monkeypatch.setattr(runtime_service, "parse_utc_iso", parse_iso)
    monkeypatch.setattr(runtime_service, "is_regular_us_equity_market_open", Mock(return_value=False))

    assert runtime_service.is_runtime_submission_window_open() is False
    parse_iso.assert_called_once_with("2026-03-14T14:00:00Z")
