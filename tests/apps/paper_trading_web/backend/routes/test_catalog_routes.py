from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.db_schema import build_db_at_head

_RUN_ENTRY = "paper_trading_web.backend.routes.catalog.run_entry"


class TestCatalogRunEndpoint:
    def test_returns_the_runner_result(self, api_client: TestClient) -> None:
        result = {"name": "report", "exitCode": 0, "output": "ok", "command": "python -m x", "timedOut": False}
        with patch(_RUN_ENTRY, return_value=result) as mocked:
            resp = api_client.post("/api/catalog/run", json={"name": "report", "values": {"account": "alpha"}})

        mocked.assert_called_once_with("report", {"account": "alpha"})
        assert resp.status_code == 200
        assert resp.json() == result

    def test_values_default_to_empty(self, api_client: TestClient) -> None:
        with patch(_RUN_ENTRY, return_value={}) as mocked:
            api_client.post("/api/catalog/run", json={"name": "list-accounts"})

        mocked.assert_called_once_with("list-accounts", {})

    def test_rejects_a_missing_name(self, api_client: TestClient) -> None:
        assert api_client.post("/api/catalog/run", json={"values": {}}).status_code == 422

    @pytest.mark.parametrize("origin", ["http://127.0.0.1:5174", "http://localhost:5173", "http://[::1]:5173"])
    def test_accepts_a_page_served_on_this_machine(self, api_client: TestClient, origin: str) -> None:
        with patch(_RUN_ENTRY, return_value={}) as mocked:
            resp = api_client.post("/api/catalog/run", json={"name": "report"}, headers={"Origin": origin})

        assert resp.status_code == 200
        mocked.assert_called_once()

    @pytest.mark.parametrize(
        "origin", ["https://evil.example", "http://192.168.1.20:5173", "http://localhost.evil.example", "null"]
    )
    def test_refuses_a_page_served_somewhere_else_without_running_anything(
        self, api_client: TestClient, origin: str
    ) -> None:
        with patch(_RUN_ENTRY, return_value={}) as mocked:
            resp = api_client.post("/api/catalog/run", json={"name": "report"}, headers={"Origin": origin})

        assert resp.status_code == 403
        mocked.assert_not_called()

    def test_maps_an_unknown_entry_to_404(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/catalog/run", json={"name": "does-not-exist"})

        assert resp.status_code == 404

    def test_maps_a_non_runnable_entry_to_400(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/catalog/run", json={"name": "create-account"})

        assert resp.status_code == 400
        assert "cannot be run from the UI" in resp.json()["detail"]

    def test_maps_bad_argument_values_to_400(self, api_client: TestClient) -> None:
        resp = api_client.post("/api/catalog/run", json={"name": "report", "values": {"shell": "x"}})

        assert resp.status_code == 400
        assert "Unknown arguments" in resp.json()["detail"]

    def test_runs_a_real_read_only_command_against_the_configured_database(
        self, api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The command runs in a child process, which finds its database through TRADING_DB_PATH.
        monkeypatch.setenv("TRADING_DB_PATH", str(build_db_at_head(tmp_path / "child.db")))

        resp = api_client.post("/api/catalog/run", json={"name": "list-accounts"})

        assert resp.status_code == 200
        assert resp.json()["exitCode"] == 0, resp.json()["output"]
