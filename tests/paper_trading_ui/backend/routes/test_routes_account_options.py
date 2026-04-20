from __future__ import annotations

from fastapi.testclient import TestClient


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
