from __future__ import annotations

from collections.abc import Callable
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


_CREATE_ACCOUNT = "paper_trading_web.backend.routes.admin.create_account_with_rotation"
_LIST_CSV_EXPORTS = "paper_trading_web.backend.routes.admin.list_csv_exports"
_PREVIEW_CSV_EXPORT = "paper_trading_web.backend.routes.admin.preview_csv_export"
_BUILD_PROMOTION_OVERVIEW = "paper_trading_web.backend.routes.admin.build_promotion_overview"
_LIST_OPERATIONS_OVERVIEW = "paper_trading_web.backend.routes.admin.list_operations_overview"


class TestAdminRoutes:
    def test_admin_create_account_happy_path(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/admin/accounts/create",
            json={
                "name": "acct_admin_create",
                "strategy": "trend",
                "initialCash": 7500,
                "benchmarkTicker": "SPY",
                "descriptiveName": "Admin Created",
                "riskPolicy": "stop_and_target",
                "stopLossPct": 4,
                "takeProfitPct": 8,
                "tradeSizePct": 12,
                "maxPositionPct": 24,
                "instrumentMode": "equity",
                "rotation": {
                    "enabled": True,
                    "schedule": ["trend", "ma_crossover", "mean_reversion"],
                    "lookbackDays": 45,
                },
            },
        )
        assert response.status_code == 200

        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["account"]["name"] == "acct_admin_create"
        assert payload["account"]["tradeSizePct"] == 12
        assert payload["account"]["maxPositionPct"] == 24
        assert payload["account"]["rotation"] == {
            "enabled": True,
            "schedule": ["trend", "ma_crossover", "mean_reversion"],
            "lookbackDays": 45,
        }

    def test_admin_delete_requires_confirmation(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": "acct_any", "confirm": False},
        )
        assert response.status_code == 400
        assert "explicit confirmation" in response.json()["detail"]

    def test_admin_delete_account_happy_path(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_admin_delete", strategy="trend")

        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": "acct_admin_delete", "confirm": True},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["deleted"]["accounts"] == 1

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

    def test_operations_overview_delegates_to_service(self, api_client: TestClient) -> None:
        expected = {"jobs": [], "artifacts": [], "backups": []}
        with patch(_LIST_OPERATIONS_OVERVIEW, Mock(return_value=expected)):
            response = api_client.get("/api/admin/operations/overview")

        assert response.status_code == 200
        assert response.json() == expected

    def test_promotion_overview_happy_path(self, api_client: TestClient, seed_account) -> None:
        seed_account("acct_promo_overview")
        expected = {"assessment": {"status": "ok"}, "evaluation": {"dataGaps": []}, "history": []}
        with patch(_BUILD_PROMOTION_OVERVIEW, Mock(return_value=expected)):
            response = api_client.get(
                "/api/admin/promotion/overview",
                params={"accountName": "acct_promo_overview"},
            )

        assert response.status_code == 200
        assert response.json() == expected

    def test_promotion_overview_includes_evaluation_detail(self, api_client: TestClient, seed_account) -> None:
        seed_account("acct_promo_evaluation")

        response = api_client.get(
            "/api/admin/promotion/overview",
            params={"accountName": "acct_promo_evaluation"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert "assessment" in payload
        assert "evaluation" in payload
        assert "history" in payload
        assert payload["evaluation"]["backtest"]["returnPct"] is None
        assert payload["evaluation"]["confidence"]["blendedScore"] is None
        assert "missing_backtest_evidence" in payload["evaluation"]["dataGaps"]

    def test_promotion_overview_missing_account_name_returns_422(self, api_client: TestClient) -> None:
        response = api_client.get("/api/admin/promotion/overview")
        assert response.status_code == 422

    def test_promotion_overview_not_found_error_returns_404(self, api_client: TestClient) -> None:
        with patch(_BUILD_PROMOTION_OVERVIEW, Mock(side_effect=ValueError("account not found"))):
            response = api_client.get(
                "/api/admin/promotion/overview",
                params={"accountName": "missing_acct"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_promotion_overview_other_value_error_returns_400(self, api_client: TestClient) -> None:
        with patch(_BUILD_PROMOTION_OVERVIEW, Mock(side_effect=ValueError("bad strategy"))):
            response = api_client.get(
                "/api/admin/promotion/overview",
                params={"accountName": "acct_any", "strategyName": "???"},
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "bad strategy"
