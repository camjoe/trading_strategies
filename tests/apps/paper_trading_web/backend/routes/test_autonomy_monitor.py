"""Tests for autonomy monitoring API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from trading.domain.exceptions import NotFoundError


def test_api_autonomy_accounts_returns_list(api_client: TestClient) -> None:
    """Test that /api/autonomy/accounts returns accounts list."""
    with patch("paper_trading_web.backend.routes.autonomy_monitor.db_conn") as mock_db:
        with patch("paper_trading_web.backend.routes.autonomy_monitor.fetch_autonomy_accounts_list") as mock_fetch:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_fetch.return_value = [
                {
                    "account_id": 1,
                    "name": "paper_account_1",
                    "total_equity": 50000.0,
                    "book_count": 2,
                },
            ]

            response = api_client.get("/api/autonomy/accounts")

            assert response.status_code == 200
            data = response.json()
            assert "accounts" in data
            assert len(data["accounts"]) == 1
            assert data["accounts"][0]["name"] == "paper_account_1"
            mock_fetch.assert_called_once_with(mock_conn)


def test_api_autonomy_account_detail_returns_data(api_client: TestClient) -> None:
    """Test that /api/autonomy/accounts/{account_name} returns account detail."""
    with patch("paper_trading_web.backend.routes.autonomy_monitor.db_conn") as mock_db:
        with patch("paper_trading_web.backend.routes.autonomy_monitor.fetch_autonomy_account_data") as mock_fetch:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_fetch.return_value = {
                "account": {
                    "account_id": 1,
                    "name": "test_account",
                    "total_equity": 50000.0,
                    "book_count": 2,
                },
                "books": [],
                "daily_workflow": {"status": "success"},
                "governance_checks": {},
                "burn_in_status": {"ready_for_live": False},
                "recent_rotations": [],
                "risk_summary": {"kill_switch_triggered": False},
            }

            response = api_client.get("/api/autonomy/accounts/test_account")

            assert response.status_code == 200
            data = response.json()
            assert data["account"]["name"] == "test_account"
            assert data["daily_workflow"]["status"] == "success"
            mock_fetch.assert_called_once_with(mock_conn, "test_account")


def test_api_autonomy_account_detail_returns_404_when_not_found(
    api_client: TestClient,
) -> None:
    """Test that 404 is returned when account not found."""
    with patch("paper_trading_web.backend.routes.autonomy_monitor.db_conn") as mock_db:
        with patch("paper_trading_web.backend.routes.autonomy_monitor.fetch_autonomy_account_data") as mock_fetch:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_conn
            mock_fetch.side_effect = NotFoundError("Account not found: nonexistent")

            response = api_client.get("/api/autonomy/accounts/nonexistent")

            assert response.status_code == 404
            data = response.json()
            assert "Account not found" in data["detail"]
