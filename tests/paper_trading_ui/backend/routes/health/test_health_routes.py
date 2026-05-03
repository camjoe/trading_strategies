from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
