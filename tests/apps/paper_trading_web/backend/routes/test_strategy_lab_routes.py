from __future__ import annotations

from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from trading.backtesting.optimizer_models import OptimizationSummary


def test_strategy_catalog_lists_primitives_and_supports_draft_lifecycle(api_client: TestClient) -> None:
    catalog = api_client.get("/api/strategy-lab/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["primitives"]

    created = api_client.post(
        "/api/strategy-lab/catalog",
        json={
            "strategyKey": "ui_test_variant",
            "primitive": "trend",
            "params": {"fast_window": 7},
            "description": "UI contract test",
        },
    )
    assert created.status_code == 200
    assert created.json()["strategy"]["status"] == "draft"

    configured = api_client.patch(
        "/api/strategy-lab/catalog/ui_test_variant",
        json={"params": {"slow_window": 25}, "enabled": False},
    )
    assert configured.status_code == 200
    assert configured.json()["strategy"]["params"] == {"fast_window": 7, "slow_window": 25}
    assert configured.json()["strategy"]["enabled"] is False

    frozen = api_client.post("/api/strategy-lab/catalog/ui_test_variant/freeze")
    assert frozen.status_code == 200
    assert frozen.json()["strategy"]["status"] == "frozen"


def test_run_optimization_delegates_to_honest_walk_forward_service(api_client: TestClient) -> None:
    summary = OptimizationSummary(
        strategy="trend",
        account_name="acct",
        objective_name="calmar_v1",
        default_params={},
        experiment_id=42,
    )
    with patch(
        "paper_trading_web.backend.routes.strategy_lab.run_and_persist_optimization",
        Mock(return_value=summary),
    ) as run_mock:
        response = api_client.post(
            "/api/strategy-lab/optimizations",
            json={
                "account": "acct",
                "strategy": "trend",
                "searchSpace": {"fast_window": [5, 10]},
                "lookbackMonths": 24,
            },
        )

    assert response.status_code == 200
    assert response.json()["experimentId"] == 42
    run_mock.assert_called_once()
