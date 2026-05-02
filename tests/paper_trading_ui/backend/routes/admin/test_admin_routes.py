from __future__ import annotations

from collections.abc import Callable
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

_CREATE_ACCOUNT = "paper_trading_ui.backend.routes.admin.create_account_with_rotation"
_LIST_CSV_EXPORTS = "paper_trading_ui.backend.routes.admin.list_csv_exports"
_PREVIEW_CSV_EXPORT = "paper_trading_ui.backend.routes.admin.preview_csv_export"


class TestAdminRoutes:
    def test_admin_delete_requires_confirmation(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": "acct_any", "confirm": False},
        )
        assert response.status_code == 400
        assert "explicit confirmation" in response.json()["detail"]

    def test_admin_delete_rejects_manual_only_account(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_manual_only", account_kind="manual_only")

        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": "acct_manual_only", "confirm": True},
        )
        assert response.status_code == 400
        assert "manual-only accounts cannot be deleted" in response.json()["detail"].lower()

    def test_admin_create_account_handles_value_error(self, api_client: TestClient) -> None:
        create_mock = Mock(side_effect=ValueError("bad payload"))
        with patch(_CREATE_ACCOUNT, create_mock):
            response = api_client.post(
                "/api/admin/accounts/create",
                json={
                    "name": "acct_bad",
                    "strategy": "trend",
                    "initialCash": 5000,
                    "benchmarkTicker": "SPY",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "bad payload"
        create_mock.assert_called_once()

    def test_admin_create_account_handles_duplicate_record(self, api_client: TestClient) -> None:
        create_mock = Mock(side_effect=ValueError("Account create failed: already exists"))
        with patch(_CREATE_ACCOUNT, create_mock):
            response = api_client.post(
                "/api/admin/accounts/create",
                json={
                    "name": "acct_dup",
                    "strategy": "trend",
                    "initialCash": 5000,
                    "benchmarkTicker": "SPY",
                },
            )

        assert response.status_code == 400
        assert "Account create failed" in response.json()["detail"]
        create_mock.assert_called_once()

    def test_admin_exports_endpoints_delegate_to_services(self, api_client: TestClient) -> None:
        list_exports_mock = Mock(return_value={"exports": [{"name": "db_csv_1", "files": []}]})
        preview_export_mock = Mock(
            return_value={
                "exportName": "db_csv_1",
                "fileName": "accounts.csv",
                "returned": 0,
                "header": [],
                "rows": [],
                "truncated": False,
            },
        )
        with patch(_LIST_CSV_EXPORTS, list_exports_mock), patch(_PREVIEW_CSV_EXPORT, preview_export_mock):
            exports_response = api_client.get("/api/admin/exports/csv")
            assert exports_response.status_code == 200
            assert exports_response.json()["exports"][0]["name"] == "db_csv_1"

            preview_response = api_client.get(
                "/api/admin/exports/csv/preview",
                params={"exportName": "db_csv_1", "fileName": "accounts.csv", "limit": 10},
            )
            assert preview_response.status_code == 200
            assert preview_response.json()["exportName"] == "db_csv_1"

        list_exports_mock.assert_called_once_with()
        preview_export_mock.assert_called_once_with("db_csv_1", "accounts.csv", 10)
