"""Tests for IBKR paper account monitoring queries."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from trading.services.ibkr_paper_monitor import queries


class MockAccount:
    """Mock account row."""

    def __init__(
        self,
        id: int,
        name: str,
        account_kind: str,
        initial_cash: float,
    ):
        self.id = id
        self.name = name
        self.account_kind = account_kind
        self.initial_cash = initial_cash


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create a mock database connection."""
    return MagicMock(spec=sqlite3.Connection)


def test_fetch_ibkr_paper_accounts_list_filters_managed_accounts(mock_conn: MagicMock) -> None:
    """Test that only managed accounts are included."""
    accounts_to_return = [
        MockAccount(id=1, name="live_account", account_kind="live", initial_cash=100000.0),
        MockAccount(id=2, name="paper_account", account_kind="managed", initial_cash=50000.0),
        MockAccount(id=3, name="another_paper", account_kind="managed", initial_cash=75000.0),
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.accounts") as mock_accounts_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
            mock_accounts_repo.get.return_value = accounts_to_return
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = []

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            # Should only include managed accounts
            assert len(result) == 2
            assert result[0]["name"] == "paper_account"
            assert result[1]["name"] == "another_paper"


def test_fetch_ibkr_paper_accounts_list_calculates_totals(mock_conn: MagicMock) -> None:
    """Test that totals are calculated correctly."""
    accounts_to_return = [
        MockAccount(id=1, name="paper_account", account_kind="managed", initial_cash=50000.0),
    ]

    sleeves_data = [
        {
            "id": 1,
            "name": "Sleeve 1",
            "current_equity": 52000.0,
            "current_cash": 10000.0,
        },
        {
            "id": 2,
            "name": "Sleeve 2",
            "current_equity": 48000.0,
            "current_cash": 5000.0,
        },
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.accounts") as mock_accounts_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
            mock_accounts_repo.get.return_value = accounts_to_return
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = sleeves_data

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            assert len(result) == 1
            account = result[0]
            assert account["total_equity"] == 100000.0  # 52000 + 48000
            assert account["total_cash"] == 15000.0  # 10000 + 5000
            assert account["positions_market_value"] == 85000.0  # 100000 - 15000
            assert account["sleeve_count"] == 2
            # return_pct: (100000 - 50000) / 50000 * 100 = 100%
            assert account["return_pct"] == 100.0


def test_fetch_ibkr_paper_accounts_list_handles_zero_initial_cash(mock_conn: MagicMock) -> None:
    """Test that return_pct is 0 when initial_cash is zero."""
    accounts_to_return = [
        MockAccount(id=1, name="zero_account", account_kind="managed", initial_cash=0.0),
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.accounts") as mock_accounts_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
            mock_accounts_repo.get.return_value = accounts_to_return
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = []

            result = queries.fetch_ibkr_paper_accounts_list(mock_conn)

            assert result[0]["return_pct"] == 0.0


def test_fetch_account_sleeves_with_metrics(mock_conn: MagicMock) -> None:
    """Test that sleeve metrics are fetched and formatted correctly."""
    sleeve_rows = [
        {
            "id": 1,
            "name": "Growth Sleeve",
            "status": "active",
            "start_equity": 50000.0,
            "current_equity": 55000.0,
            "current_cash": 5000.0,
        },
    ]

    metrics_rows = [
        {
            "hit_rate": 0.65,
            "drawdown_pct": -10.5,
            "trade_count": 25,
            "metric_date": "2026-05-10",
        },
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.DailyMetricsRepository") as mock_repo_class:
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = sleeve_rows
            mock_repo_class.return_value.fetch_for_sleeve.return_value = metrics_rows

            result = queries._fetch_account_sleeves(mock_conn, account_id=1)

            assert len(result) == 1
            sleeve = result[0]
            assert sleeve["name"] == "Growth Sleeve"
            assert sleeve["current_equity"] == 55000.0
            assert sleeve["latest_metrics"]["hit_rate"] == 0.65
            assert sleeve["latest_metrics"]["trade_count"] == 25
            # return_pct: (55000 - 50000) / 50000 * 100 = 10%
            assert sleeve["return_pct"] == 10.0


def test_fetch_account_sleeves_without_metrics(mock_conn: MagicMock) -> None:
    """Test that missing metrics are handled gracefully."""
    sleeve_rows = [
        {
            "id": 1,
            "name": "New Sleeve",
            "status": "active",
            "start_equity": 50000.0,
            "current_equity": 50000.0,
            "current_cash": 50000.0,
        },
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.DailyMetricsRepository") as mock_repo_class:
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = sleeve_rows
            mock_repo_class.return_value.fetch_for_sleeve.return_value = []

            result = queries._fetch_account_sleeves(mock_conn, account_id=1)

            sleeve = result[0]
            assert sleeve["latest_metrics"]["hit_rate"] is None
            assert sleeve["latest_metrics"]["trade_count"] == 0
            assert sleeve["latest_metrics"]["metric_date"] is None


def test_fetch_recent_rotations(mock_conn: MagicMock) -> None:
    """Test that recent rotations are fetched and sorted correctly."""
    sleeve_rows = [
        {"id": 1, "name": "Growth Sleeve"},
        {"id": 2, "name": "Value Sleeve"},
    ]

    rotation_rows_1 = [
        {
            "id": 101,
            "incumbent_strategy": "momentum",
            "challenger_strategy": "mean_reversion",
            "decision_time": "2026-05-10T10:00:00",
            "decision_reason": "Underperformance",
        },
    ]

    rotation_rows_2 = [
        {
            "id": 102,
            "incumbent_strategy": "div_yield",
            "challenger_strategy": "growth",
            "decision_time": "2026-05-11T14:00:00",
            "decision_reason": "Better alpha",
        },
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.sleeves") as mock_sleeves_repo:
        with patch("trading.services.ibkr_paper_monitor.queries.RotationDecisionRepository") as mock_repo_class:
            mock_sleeves_repo.fetch_strategy_sleeves_for_account.return_value = sleeve_rows
            mock_repo_class.return_value.fetch_for_sleeve.side_effect = [
                rotation_rows_1,
                rotation_rows_2,
            ]

            result = queries._fetch_recent_rotations(mock_conn, account_id=1)

            # Should be sorted by decision_time descending
            assert len(result) == 2
            assert result[0]["decision_time"] == "2026-05-11T14:00:00"
            assert result[1]["decision_time"] == "2026-05-10T10:00:00"


def test_fetch_risk_summary_detects_kill_switch(mock_conn: MagicMock) -> None:
    """Test that kill switch is detected when action is 'block'."""
    risk_rows = [
        {
            "id": 1,
            "symbol": "AAPL",
            "side": "BUY",
            "action": "block",
            "reason_code": "risk_limit_exceeded",
            "approved_notional": 0.0,
            "requested_notional": 10000.0,
        },
    ]

    with patch("trading.services.ibkr_paper_monitor.queries.sleeve_risk_decisions") as mock_risk_repo:
        mock_risk_repo.fetch_sleeve_risk_decisions_for_account.return_value = risk_rows

        result = queries._fetch_risk_summary(mock_conn, account_id=1)

        assert result["kill_switch_triggered"] is True
        assert len(result["violations"]) == 1
        assert result["violations"][0]["action"] == "block"


def test_fetch_ibkr_paper_account_detail_raises_on_missing_account(
    mock_conn: MagicMock,
) -> None:
    """Test that ValueError is raised when account not found."""
    with patch("trading.services.ibkr_paper_monitor.queries.accounts") as mock_accounts_repo:
        mock_accounts_repo.get_by_name.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            queries.fetch_ibkr_paper_account_detail(mock_conn, "nonexistent")


def test_fetch_ibkr_paper_account_detail_aggregates_all_data(
    mock_conn: MagicMock,
) -> None:
    """Test that account detail aggregates sleeves, rotations, and risk data."""
    account = MockAccount(id=1, name="test_account", account_kind="managed", initial_cash=50000.0)

    with patch("trading.services.ibkr_paper_monitor.queries.accounts") as mock_accounts_repo:
        with patch("trading.services.ibkr_paper_monitor.queries._fetch_account_sleeves") as mock_fetch_sleeves:
            with patch("trading.services.ibkr_paper_monitor.queries._fetch_recent_rotations") as mock_fetch_rotations:
                with patch("trading.services.ibkr_paper_monitor.queries._fetch_risk_summary") as mock_fetch_risk:
                    mock_accounts_repo.get_by_name.return_value = account
                    mock_fetch_sleeves.return_value = [
                        {
                            "sleeve_id": 1,
                            "name": "Sleeve 1",
                            "current_equity": 55000.0,
                            "current_cash": 10000.0,
                        },
                    ]
                    mock_fetch_rotations.return_value = []
                    mock_fetch_risk.return_value = {"kill_switch_triggered": False}

                    result = queries.fetch_ibkr_paper_account_detail(mock_conn, "test_account")

                    assert result["account"]["name"] == "test_account"
                    assert result["account"]["total_equity"] == 55000.0
                    assert result["account"]["sleeve_count"] == 1
                    assert result["sleeves"] == mock_fetch_sleeves.return_value
                    assert result["recent_rotations"] == []
                    assert result["risk_summary"] == {"kill_switch_triggered": False}
