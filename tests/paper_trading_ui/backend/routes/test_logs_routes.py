from __future__ import annotations

from fastapi.testclient import TestClient

from apps.paper_trading_ui.backend.routes import logs as logs_routes


class TestLogsRoutes:
    def test_logs_endpoints_file_listing_and_filter(self, monkeypatch, tmp_path, api_client: TestClient) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "app.log").write_text("INFO start\nERROR failed\nINFO done\n", encoding="utf-8")
        (log_dir / "other.log").write_text("line\n", encoding="utf-8")
        monkeypatch.setattr(logs_routes, "LOGS_DIR", log_dir)

        files_response = api_client.get("/api/logs/files")
        assert files_response.status_code == 200
        assert files_response.json()["files"] == ["other.log", "app.log"]

        read_response = api_client.get("/api/logs/app.log", params={"limit": 50, "contains": "error"})
        assert read_response.status_code == 200
        payload = read_response.json()
        assert payload["lineCount"] == 1
        assert payload["lines"] == ["ERROR failed"]

    def test_logs_file_endpoint_not_found(self, monkeypatch, tmp_path, api_client: TestClient) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(logs_routes, "LOGS_DIR", log_dir)

        response = api_client.get("/api/logs/missing.log")
        assert response.status_code == 404

    def test_logs_file_endpoint_rejects_invalid_path(self, monkeypatch, tmp_path, api_client: TestClient) -> None:
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(logs_routes, "LOGS_DIR", log_dir)

        response = api_client.get("/api/logs/..%5Coutside.log")
        assert response.status_code == 400
