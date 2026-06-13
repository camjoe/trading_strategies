"""Tests for IBKR paper account monitoring queries."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from trading.services.ibkr_paper_monitor import queries


def _make_sleeve(
    *,
    id: int = 1,
    name: str = "Sleeve 1",
    status: str = "active",
    start_equity: float = 50_000.0,
    current_equity: float = 52_000.0,
    current_cash: float = 10_000.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        status=status,
        start_equity=start_equity,
        current_equity=current_equity,
        current_cash=current_cash,
    )


def _make_account(
    *,
    id: int = 1,
    name: str = "paper_account",
    account_kind: str = "managed",
    initial_cash: float = 50_000.0,
) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name, account_kind=account_kind, initial_cash=initial_cash)


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


def test_fetch_ibkr_paper_accounts_list_filters_managed_accounts(mock_conn: MagicMock) -> None:
    accounts = [
        _make_account(id=1, name="live_account", account_kind="live"),
        _make_account(id=2, name="paper_account", account_kind="managed"),
        _make_account(id=3, name="another_paper", account_kind="managed"),
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
            mock_acct_cls.return_value.fetch_all.return_value = accounts
            mock_sleeve_cls.return_value.fetch_for_account.return_value = []

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            assert len(result) == 2
            assert result[0]["name"] == "paper_account"
            assert result[1]["name"] == "another_paper"


def test_fetch_ibkr_paper_accounts_list_calculates_totals(mock_conn: MagicMock) -> None:
    accounts = [_make_account(id=1, name="paper_account", initial_cash=50_000.0)]
    sleeves = [
        _make_sleeve(id=1, current_equity=52_000.0, current_cash=10_000.0),
        _make_sleeve(id=2, current_equity=48_000.0, current_cash=5_000.0),
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
            mock_acct_cls.return_value.fetch_all.return_value = accounts
            mock_sleeve_cls.return_value.fetch_for_account.return_value = sleeves

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            assert len(result) == 1
            account = result[0]
            assert account["total_equity"] == 100_000.0
            assert account["total_cash"] == 15_000.0
            assert account["positions_market_value"] == 85_000.0
            assert account["sleeve_count"] == 2
            assert account["return_pct"] == 100.0


def test_fetch_ibkr_paper_accounts_list_handles_zero_initial_cash(mock_conn: MagicMock) -> None:
    accounts = [_make_account(id=1, name="zero_account", initial_cash=0.0)]

    with patch("trading.services.ibkr_paper_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
            mock_acct_cls.return_value.fetch_all.return_value = accounts
            mock_sleeve_cls.return_value.fetch_for_account.return_value = []

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            assert result[0]["return_pct"] == 0.0


def test_fetch_account_sleeves_with_metrics(mock_conn: MagicMock) -> None:
    sleeves = [_make_sleeve(id=1, name="Growth Sleeve", start_equity=50_000.0, current_equity=55_000.0, current_cash=5_000.0)]

    metric = SimpleNamespace(hit_rate=0.65, drawdown_pct=-10.5, trade_count=25, metric_date="2026-05-10")

    with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.DailyMetricsRepository") as mock_metrics_cls:
            mock_sleeve_cls.return_value.fetch_for_account.return_value = sleeves
            mock_metrics_cls.return_value.fetch_for_sleeve.return_value = [metric]

            result = queries._fetch_account_sleeves(mock_conn, account_id=1)

            assert len(result) == 1
            sleeve = result[0]
            assert sleeve["name"] == "Growth Sleeve"
            assert sleeve["current_equity"] == 55_000.0
            assert sleeve["latest_metrics"]["hit_rate"] == 0.65
            assert sleeve["latest_metrics"]["trade_count"] == 25
            assert sleeve["return_pct"] == 10.0


def test_fetch_account_sleeves_without_metrics(mock_conn: MagicMock) -> None:
    sleeves = [_make_sleeve(id=1, name="New Sleeve", start_equity=50_000.0, current_equity=50_000.0, current_cash=50_000.0)]

    with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.DailyMetricsRepository") as mock_metrics_cls:
            mock_sleeve_cls.return_value.fetch_for_account.return_value = sleeves
            mock_metrics_cls.return_value.fetch_for_sleeve.return_value = []

            result = queries._fetch_account_sleeves(mock_conn, account_id=1)

            sleeve = result[0]
            assert sleeve["latest_metrics"]["hit_rate"] is None
            assert sleeve["latest_metrics"]["trade_count"] == 0
            assert sleeve["latest_metrics"]["metric_date"] is None


def test_fetch_recent_rotations(mock_conn: MagicMock) -> None:
    sleeves = [
        _make_sleeve(id=1, name="Growth Sleeve"),
        _make_sleeve(id=2, name="Value Sleeve"),
    ]

    rotation_1 = {"id": 101, "incumbent_strategy": "momentum", "challenger_strategy": "mean_reversion",
                  "decision_time": "2026-05-10T10:00:00", "decision_reason": "Underperformance"}
    rotation_2 = {"id": 102, "incumbent_strategy": "div_yield", "challenger_strategy": "growth",
                  "decision_time": "2026-05-11T14:00:00", "decision_reason": "Better alpha"}

    with patch("trading.services.ibkr_paper_monitor.queries.SleeveRepository") as mock_sleeve_cls:
        with patch("trading.services.ibkr_paper_monitor.queries.RotationDecisionRepository") as mock_rot_cls:
            mock_sleeve_cls.return_value.fetch_for_account.return_value = sleeves
            mock_rot_cls.return_value.fetch_for_sleeve.side_effect = [[rotation_1], [rotation_2]]

            result = queries._fetch_recent_rotations(mock_conn, account_id=1)

            assert len(result) == 2
            assert result[0]["decision_time"] == "2026-05-11T14:00:00"
            assert result[1]["decision_time"] == "2026-05-10T10:00:00"


def test_fetch_risk_summary_detects_kill_switch(mock_conn: MagicMock) -> None:
    decisions = [_make_risk_decision(id=1, symbol="AAPL", side="buy", action="block",
                                     reason_code="risk_limit_exceeded", approved_notional=0.0, requested_notional=10_000.0)]

    with patch("trading.services.ibkr_paper_monitor.queries.SleeveRiskDecisionRepository") as mock_risk_cls:
        mock_risk_cls.return_value.fetch_for_account.return_value = decisions

        result = queries._fetch_risk_summary(mock_conn, account_id=1)

        assert result["kill_switch_triggered"] is True
        assert len(result["violations"]) == 1
        assert result["violations"][0]["action"] == "block"


def test_fetch_ibkr_paper_account_detail_raises_on_missing_account(mock_conn: MagicMock) -> None:
    with patch("trading.services.ibkr_paper_monitor.queries.AccountRepository") as mock_acct_cls:
        mock_acct_cls.return_value.fetch_by_name.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            queries.fetch_ibkr_paper_account_detail(mock_conn, "nonexistent")


def test_fetch_ibkr_paper_account_detail_aggregates_all_data(mock_conn: MagicMock) -> None:
    account = _make_account(id=1, name="test_account", initial_cash=50_000.0)

    with patch("trading.services.ibkr_paper_monitor.queries.AccountRepository") as mock_acct_cls:
        with patch("trading.services.ibkr_paper_monitor.queries._fetch_account_sleeves") as mock_fetch_sleeves:
            with patch("trading.services.ibkr_paper_monitor.queries._fetch_recent_rotations") as mock_fetch_rotations:
                with patch("trading.services.ibkr_paper_monitor.queries._fetch_risk_summary") as mock_fetch_risk:
                    mock_acct_cls.return_value.fetch_by_name.return_value = account
                    mock_fetch_sleeves.return_value = [{"sleeve_id": 1, "name": "Sleeve 1",
                                                        "current_equity": 55_000.0, "current_cash": 10_000.0}]
                    mock_fetch_rotations.return_value = []
                    mock_fetch_risk.return_value = {"kill_switch_triggered": False}

                    result = queries.fetch_ibkr_paper_account_detail(mock_conn, "test_account")

                    assert result["account"]["name"] == "test_account"
                    assert result["account"]["total_equity"] == 55_000.0
                    assert result["account"]["sleeve_count"] == 1
                    assert result["sleeves"] == mock_fetch_sleeves.return_value
                    assert result["recent_rotations"] == []
                    assert result["risk_summary"] == {"kill_switch_triggered": False}
