from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
import pytest

def test_account_config_options_endpoint_returns_canonical_choices(api_client: TestClient) -> None:
    response = api_client.get("/api/accounts/config/options")
    assert response.status_code == 200

    payload = response.json()
    assert payload["goalPeriods"] == ["monthly", "weekly", "quarterly", "yearly"]
    assert payload["riskPolicies"] == ["none", "fixed_stop", "take_profit", "stop_and_target"]
    assert payload["instrumentModes"] == ["equity", "leaps"]
    assert payload["optionTypes"] == ["call", "put", "both"]
    assert payload["rotationModes"] == ["time", "optimal", "regime"]
    assert payload["rotationOptimalityModes"] == ["previous_period_best", "average_return", "hybrid_weighted"]
    assert payload["rotationOverlayModes"] == ["none", "news", "social", "news_social"]
    assert payload["defaults"]["goalPeriod"] == "monthly"
    assert payload["defaults"]["riskPolicy"] == "none"
    assert payload["defaults"]["instrumentMode"] == "equity"


def test_accounts_endpoint_lists_visible_accounts(
    api_client: TestClient,
    seed_account: Callable[..., None],
) -> None:
    seed_account("acct_listed")

    response = api_client.get("/api/accounts")
    assert response.status_code == 200

    accounts = response.json()["accounts"]
    names = [item["name"] for item in accounts]
    assert "acct_listed" in names
    listed = next(item for item in accounts if item["name"] == "acct_listed")
    assert "instrumentMode" in listed
    assert "optionMinDte" not in listed
    assert "rotationOverlayWatchlist" not in listed


def test_account_detail_known_account(api_client: TestClient, seed_account: Callable[..., None]) -> None:
    seed_account("acct_detail")

    response = api_client.get("/api/accounts/acct_detail")
    assert response.status_code == 200

    payload = response.json()
    assert payload["account"]["name"] == "acct_detail"
    assert isinstance(payload["trades"], list)
    assert isinstance(payload["snapshots"], list)


def test_accounts_compare_lists_visible_accounts(
    api_client: TestClient,
    seed_account: Callable[..., None],
) -> None:
    seed_account("acct_compare_visible")

    response = api_client.get("/api/accounts/compare")
    assert response.status_code == 200

    names = [item["name"] for item in response.json()["accounts"]]
    assert "acct_compare_visible" in names


class TestAccountParamsEndpoint:
    def test_patch_params_updates_strategy(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_strategy")

        resp = api_client.patch(
            "/api/accounts/acct_params_strategy/params",
            json={"strategy": "mean_reversion"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        detail = api_client.get("/api/accounts/acct_params_strategy").json()
        assert detail["account"]["strategy"] == "mean_reversion"

    def test_patch_params_updates_risk_policy(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_risk")

        resp = api_client.patch(
            "/api/accounts/acct_params_risk/params",
            json={"riskPolicy": "fixed_stop"},
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_risk").json()
        assert detail["account"]["riskPolicy"] == "fixed_stop"

    def test_patch_params_updates_position_sizing(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_sizing")

        resp = api_client.patch(
            "/api/accounts/acct_params_sizing/params",
            json={"tradeSizePct": 11.5, "maxPositionPct": 22.5},
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_sizing").json()
        assert detail["account"]["tradeSizePct"] == pytest.approx(11.5)
        assert detail["account"]["maxPositionPct"] == pytest.approx(22.5)

    def test_patch_params_empty_body_is_no_op(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_noop")

        resp = api_client.patch("/api/accounts/acct_params_noop/params", json={})
        assert resp.status_code == 200

    def test_patch_params_unknown_account_returns_404(self, api_client: TestClient) -> None:
        resp = api_client.patch(
            "/api/accounts/no_such_account/params",
            json={"strategy": "trend"},
        )
        assert resp.status_code == 404

    def test_patch_params_invalid_risk_policy_returns_422(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_invalid_risk")

        resp = api_client.patch(
            "/api/accounts/acct_params_invalid_risk/params",
            json={"riskPolicy": "not_a_real_policy"},
        )
        assert resp.status_code == 422

    def test_patch_params_invalid_goal_range_returns_422(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_invalid_goal")

        resp = api_client.patch(
            "/api/accounts/acct_params_invalid_goal/params",
            json={"goalMinReturnPct": 0.50, "goalMaxReturnPct": 0.10},
        )
        assert resp.status_code == 422

    def test_patch_params_updates_rotation_fields(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_params_rotation")

        resp = api_client.patch(
            "/api/accounts/acct_params_rotation/params",
            json={
                "rotationEnabled": True,
                "rotationMode": "regime",
                "rotationOptimalityMode": "average_return",
                "rotationIntervalDays": 7,
                "rotationIntervalMinutes": 240,
                "rotationLookbackDays": 30,
                "rotationSchedule": ["trend", "ma_crossover", "mean_reversion"],
                "rotationRegimeStrategyRiskOn": "trend",
                "rotationRegimeStrategyNeutral": "ma_crossover",
                "rotationRegimeStrategyRiskOff": "mean_reversion",
                "rotationOverlayMode": "news_social",
                "rotationOverlayMinTickers": 2,
                "rotationOverlayConfidenceThreshold": 0.55,
                "rotationOverlayWatchlist": ["AAPL", "MSFT", "NVDA"],
                "rotationActiveIndex": 1,
                "rotationActiveStrategy": "ma_crossover",
                "rotationLastAt": "2026-03-20T00:00:00Z",
            },
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_rotation").json()
        account = detail["account"]
        assert account["rotationEnabled"] is True
        assert account["rotationMode"] == "regime"
        assert account["rotationOptimalityMode"] == "average_return"
        assert account["rotationIntervalDays"] == 7
        assert account["rotationIntervalMinutes"] == 240
        assert account["rotationLookbackDays"] == 30
        assert account["rotationSchedule"] == ["trend", "ma_crossover", "mean_reversion"]
        assert account["rotationRegimeStrategyRiskOn"] == "trend"
        assert account["rotationRegimeStrategyNeutral"] == "ma_crossover"
        assert account["rotationRegimeStrategyRiskOff"] == "mean_reversion"
        assert account["rotationOverlayMode"] == "news_social"
        assert account["rotationOverlayMinTickers"] == 2
        assert account["rotationOverlayConfidenceThreshold"] == pytest.approx(0.55)
        assert account["rotationOverlayWatchlist"] == ["AAPL", "MSFT", "NVDA"]
        assert account["rotationActiveIndex"] == 1
        assert account["rotationActiveStrategy"] == "ma_crossover"
        assert account["rotationLastAt"] == "2026-03-20T00:00:00Z"
