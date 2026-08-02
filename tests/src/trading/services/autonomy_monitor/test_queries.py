"""Tests for autonomy monitoring queries."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from trading.services.autonomy_monitor import queries


def _make_book(
    *,
    id: int = 1,
    name: str = "Book 1",
    status: str = "active",
    is_default: int = 0,
    start_equity: float = 50_000.0,
    current_equity: float = 52_000.0,
    current_cash: float = 10_000.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        status=status,
        is_default=is_default,
        start_equity=start_equity,
        current_equity=current_equity,
        current_cash=current_cash,
    )


def _make_account(
    *,
    id: int = 1,
    name: str = "paper_account",
    initial_cash: float = 50_000.0,
) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name, initial_cash=initial_cash)


def _make_risk_decision(
    *,
    id: int = 1,
    symbol: str = "AAPL",
    side: str = "buy",
    action: str = "allow",
    reason_code: str = "ok",
    approved_notional: float = 1000.0,
    requested_notional: float = 1000.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        symbol=symbol,
        side=side,
        action=action,
        reason_code=reason_code,
        approved_notional=approved_notional,
        requested_notional=requested_notional,
    )


@pytest.fixture
def mock_conn() -> MagicMock:
    return MagicMock(spec=sqlite3.Connection)


def test_fetch_autonomy_accounts_list_returns_every_account(mock_conn: MagicMock) -> None:
    accounts = [
        _make_account(id=1, name="paper_account"),
        _make_account(id=2, name="another_paper"),
    ]

    with patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.autonomy_monitor.queries.BookRepository") as mock_book_cls:
            with patch("trading.services.autonomy_monitor.queries.list_report_books", return_value=[]):
                mock_acct_cls.return_value.fetch_all.return_value = accounts
                mock_book_cls.return_value.fetch_for_account.return_value = []

                result = queries.fetch_autonomy_accounts_list(mock_conn)

            assert len(result) == 2
            assert result[0]["name"] == "paper_account"
            assert result[1]["name"] == "another_paper"


def test_fetch_autonomy_accounts_list_calculates_totals(mock_conn: MagicMock) -> None:
    accounts = [_make_account(id=1, name="paper_account", initial_cash=50_000.0)]
    books = [
        _make_book(id=1, current_equity=52_000.0, current_cash=10_000.0),
        _make_book(id=2, current_equity=48_000.0, current_cash=5_000.0),
    ]

    with patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.autonomy_monitor.queries.BookRepository") as mock_book_cls:
            with patch(
                "trading.services.autonomy_monitor.queries.list_report_books",
                return_value=[(b, None) for b in books],
            ):
                mock_acct_cls.return_value.fetch_all.return_value = accounts
                mock_book_cls.return_value.fetch_for_account.return_value = books

                result = queries.fetch_autonomy_accounts_list(mock_conn)

        assert len(result) == 1
        account = result[0]
        # Account totals roll up the book balances.
        assert account["total_equity"] == 100_000.0
        assert account["total_cash"] == 15_000.0
        assert account["positions_market_value"] == 85_000.0
        assert account["book_count"] == 2
        assert account["return_pct"] == 100.0


def test_fetch_autonomy_accounts_list_handles_zero_initial_cash(mock_conn: MagicMock) -> None:
    accounts = [_make_account(id=1, name="zero_account", initial_cash=0.0)]

    with patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.autonomy_monitor.queries.BookRepository") as mock_book_cls:
            with patch("trading.services.autonomy_monitor.queries.list_report_books", return_value=[]):
                mock_acct_cls.return_value.fetch_all.return_value = accounts
                mock_book_cls.return_value.fetch_for_account.return_value = []

                result = queries.fetch_autonomy_accounts_list(mock_conn)

        assert result[0]["return_pct"] == 0.0


def test_fetch_account_books_with_metrics(mock_conn: MagicMock) -> None:
    books = [
        _make_book(id=1, name="Growth Book", start_equity=50_000.0, current_equity=55_000.0, current_cash=5_000.0)
    ]
    metric = SimpleNamespace(hit_rate=0.65, drawdown_pct=-10.5, trade_count=25, metric_date="2026-05-10")
    assignment = SimpleNamespace(strategy_name="momentum")

    with patch(
        "trading.services.autonomy_monitor.queries.list_report_books",
        return_value=[(b, assignment) for b in books],
    ):
        with patch("trading.services.autonomy_monitor.queries.DailyMetricsRepository") as mock_metrics_cls:
            mock_metrics_cls.return_value.fetch_for_book.return_value = [metric]

            result = queries._fetch_account_books(mock_conn, account_id=1)

            assert len(result) == 1
            book = result[0]
            assert book["name"] == "Growth Book"
            assert book["strategy"] == "momentum"
            assert book["current_equity"] == 55_000.0
            assert book["latest_metrics"]["hit_rate"] == 0.65
            assert book["latest_metrics"]["trade_count"] == 25
            assert book["return_pct"] == 10.0


def test_fetch_account_books_without_metrics(mock_conn: MagicMock) -> None:
    books = [_make_book(id=1, name="New Book", start_equity=50_000.0, current_equity=50_000.0, current_cash=50_000.0)]

    with patch(
        "trading.services.autonomy_monitor.queries.list_report_books",
        return_value=[(b, None) for b in books],
    ):
        with patch("trading.services.autonomy_monitor.queries.DailyMetricsRepository") as mock_metrics_cls:
            mock_metrics_cls.return_value.fetch_for_book.return_value = []

            result = queries._fetch_account_books(mock_conn, account_id=1)

            book = result[0]
            assert book["strategy"] == "unassigned"
            assert book["latest_metrics"]["hit_rate"] is None
            assert book["latest_metrics"]["trade_count"] == 0
            assert book["latest_metrics"]["metric_date"] is None


def test_fetch_recent_rotations(mock_conn: MagicMock) -> None:
    books = [
        _make_book(id=1, name="Growth Book"),
        _make_book(id=2, name="Value Book"),
    ]

    rotation_1 = SimpleNamespace(
        id=101,
        incumbent_strategy="momentum",
        challenger_strategy="mean_reversion",
        decision_time="2026-05-10T10:00:00",
        decision_reason="Underperformance",
    )
    rotation_2 = SimpleNamespace(
        id=102,
        incumbent_strategy="div_yield",
        challenger_strategy="growth",
        decision_time="2026-05-11T14:00:00",
        decision_reason="Better alpha",
    )

    with patch(
        "trading.services.autonomy_monitor.queries.list_report_books",
        return_value=[(b, None) for b in books],
    ):
        with patch("trading.services.autonomy_monitor.queries.RotationDecisionRepository") as mock_rot_cls:
            mock_rot_cls.return_value.fetch_for_book.side_effect = [[rotation_1], [rotation_2]]

            result = queries._fetch_recent_rotations(mock_conn, account_id=1)

            assert len(result) == 2
            assert result[0]["decision_time"] == "2026-05-11T14:00:00"
            assert result[0]["book_name"] == "Value Book"
            assert result[1]["decision_time"] == "2026-05-10T10:00:00"


def test_fetch_risk_summary_detects_kill_switch(mock_conn: MagicMock) -> None:
    decisions = [
        _make_risk_decision(
            id=1,
            symbol="AAPL",
            side="buy",
            action="block",
            reason_code="risk_limit_exceeded",
            approved_notional=0.0,
            requested_notional=10_000.0,
        )
    ]

    with patch("trading.services.autonomy_monitor.queries.RiskDecisionRepository") as mock_risk_cls:
        mock_risk_cls.return_value.fetch_recent.return_value = decisions

        result = queries._fetch_risk_summary(mock_conn, account_id=1)

        assert result["kill_switch_triggered"] is True
        assert len(result["violations"]) == 1
        assert result["violations"][0]["action"] == "block"


def test_fetch_autonomy_account_detail_raises_on_missing_account(mock_conn: MagicMock) -> None:
    with patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls:
        mock_acct_cls.return_value.fetch_by_name.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            queries.fetch_autonomy_account_detail(mock_conn, "nonexistent")


def test_fetch_autonomy_account_detail_aggregates_all_data(mock_conn: MagicMock) -> None:
    account = _make_account(id=1, name="test_account", initial_cash=50_000.0)
    sleeve = _make_book(id=2, name="Book 1", current_equity=55_000.0, current_cash=10_000.0)

    books_payload = [{"book_id": 2, "name": "Book 1", "current_equity": 55_000.0, "current_cash": 10_000.0}]

    with (
        patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls,
        patch("trading.services.autonomy_monitor.queries.BookRepository") as mock_book_cls,
        patch("trading.services.autonomy_monitor.queries._fetch_account_books", return_value=books_payload),
        patch("trading.services.autonomy_monitor.queries.list_report_books", return_value=[(sleeve, None)]),
        patch("trading.services.autonomy_monitor.queries._fetch_recent_rotations", return_value=[]),
        patch(
            "trading.services.autonomy_monitor.queries._fetch_risk_summary",
            return_value={"kill_switch_triggered": False},
        ),
    ):
        mock_acct_cls.return_value.fetch_by_name.return_value = account
        mock_book_cls.return_value.fetch_for_account.return_value = [sleeve]

        result = queries.fetch_autonomy_account_detail(mock_conn, "test_account")

    assert result["account"]["name"] == "test_account"
    assert result["account"]["total_equity"] == 55_000.0
    assert result["account"]["book_count"] == 1
    assert result["books"] == books_payload
    assert result["recent_rotations"] == []
    assert result["risk_summary"] == {"kill_switch_triggered": False}


def test_fetch_autonomy_account_detail_totals_include_the_default_book(mock_conn: MagicMock) -> None:
    """Account totals span every book, so the return matches ``initial_cash``.

    The books panel lists only the non-default sleeves. Rolling the headline
    equity over that same subset would measure sleeve equity against the whole
    account's capital — the parent account's own book holds the rest.
    """
    account = _make_account(id=1, name="multi_book", initial_cash=40_000.0)
    default_book = _make_book(id=1, name="default", is_default=1, current_equity=16_000.0, current_cash=15_000.0)
    sleeve = _make_book(id=2, name="growth_sleeve", current_equity=25_000.0, current_cash=20_000.0)

    with (
        patch("trading.services.autonomy_monitor.queries.AccountRepository") as mock_acct_cls,
        patch("trading.services.autonomy_monitor.queries.BookRepository") as mock_book_cls,
        patch("trading.services.autonomy_monitor.queries._fetch_account_books", return_value=[]),
        patch("trading.services.autonomy_monitor.queries.list_report_books", return_value=[(sleeve, None)]),
        patch("trading.services.autonomy_monitor.queries._fetch_recent_rotations", return_value=[]),
        patch("trading.services.autonomy_monitor.queries._fetch_risk_summary", return_value={}),
    ):
        mock_acct_cls.return_value.fetch_by_name.return_value = account
        mock_book_cls.return_value.fetch_for_account.return_value = [default_book, sleeve]

        overview = queries.fetch_autonomy_account_detail(mock_conn, "multi_book")["account"]

    assert overview["total_equity"] == 41_000.0
    assert overview["total_cash"] == 35_000.0
    assert overview["positions_market_value"] == 6_000.0
    # +2.5% on 40k, not the -37.5% that sleeve-only equity would have reported.
    assert overview["return_pct"] == 2.5
    # The panel below the overview still lists the sleeves only.
    assert overview["book_count"] == 1
