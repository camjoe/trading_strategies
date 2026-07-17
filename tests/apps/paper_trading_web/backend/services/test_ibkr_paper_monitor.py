"""Tests for UI backend IBKR paper account monitoring service."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from paper_trading_web.backend.services import ibkr_paper_monitor as service


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create a mock database connection."""
    return MagicMock(spec=sqlite3.Connection)


def test_fetch_ibkr_paper_accounts_list_delegates_to_trading_service(
    mock_conn: MagicMock,
) -> None:
    """Test that accounts list is delegated to trading service."""
    expected_accounts = [
        {
            "account_id": 1,
            "name": "paper_account_1",
            "total_equity": 50000.0,
            "book_count": 2,
        },
    ]

    with patch("paper_trading_web.backend.services.ibkr_paper_monitor.fetch_db_accounts_list") as mock_fetch:
        mock_fetch.return_value = expected_accounts

        result = service.fetch_ibkr_paper_accounts_list(mock_conn)

        assert result == expected_accounts
        mock_fetch.assert_called_once_with(mock_conn)


def test_fetch_account_ibkr_paper_monitor_data_aggregates_db_and_artifacts(
    mock_conn: MagicMock,
) -> None:
    """Test that dashboard data combines DB data with artifact data."""
    db_data = {
        "account": {
            "account_id": 1,
            "name": "test_account",
            "total_equity": 50000.0,
            "book_count": 2,
        },
        "books": [],
        "recent_rotations": [],
        "risk_summary": {"kill_switch_triggered": False},
    }

    workflow_data = {
        "status": "success",
        "latest_run_time": "2026-05-10T09:30:00Z",
        "completed_steps": 3,
    }

    governance_data = {
        "w1_leaderboard": {"status": "success", "last_run": "2026-05-10T10:00:00Z"},
        "w2_promotion": {"status": "not_run", "last_run": None},
    }

    burn_in_data = {
        "ready_for_live": True,
        "consecutive_successes": 15,
        "min_required_successes": 10,
    }

    with patch("paper_trading_web.backend.services.ibkr_paper_monitor.fetch_db_data") as mock_db:
        with patch(
            "paper_trading_web.backend.services.ibkr_paper_monitor.fetch_daily_workflow_status"
        ) as mock_workflow:
            with patch(
                "paper_trading_web.backend.services.ibkr_paper_monitor.fetch_governance_checks_status"
            ) as mock_governance:
                with patch(
                    "paper_trading_web.backend.services.ibkr_paper_monitor.fetch_burn_in_status"
                ) as mock_burn_in:
                    mock_db.return_value = db_data
                    mock_workflow.return_value = workflow_data
                    mock_governance.return_value = governance_data
                    mock_burn_in.return_value = burn_in_data

                    result = service.fetch_account_ibkr_paper_monitor_data(mock_conn, "test_account")

                    # Check that DB data is present
                    assert result["account"]["name"] == "test_account"
                    assert result["books"] == []
                    assert result["recent_rotations"] == []

                    # Check that artifact data is present
                    assert result["daily_workflow"] == workflow_data
                    assert result["governance_checks"] == governance_data
                    assert result["burn_in_status"] == burn_in_data

                    # Verify all service functions were called
                    mock_db.assert_called_once_with(mock_conn, "test_account")
                    mock_workflow.assert_called_once()
                    mock_governance.assert_called_once()
                    mock_burn_in.assert_called_once()


def test_fetch_account_ibkr_paper_monitor_data_raises_on_missing_account(
    mock_conn: MagicMock,
) -> None:
    """Test that ValueError is propagated when account not found."""
    with patch("paper_trading_web.backend.services.ibkr_paper_monitor.fetch_db_data") as mock_db:
        mock_db.side_effect = ValueError("Account not found: nonexistent")

        with pytest.raises(ValueError, match="Account not found"):
            service.fetch_account_ibkr_paper_monitor_data(mock_conn, "nonexistent")
