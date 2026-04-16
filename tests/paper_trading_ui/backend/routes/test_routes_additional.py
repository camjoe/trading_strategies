from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from common.time import utc_now_iso
from paper_trading_ui.backend.config import TEST_ACCOUNT_NAME
from paper_trading_ui.backend.routes import admin as admin_routes
from paper_trading_ui.backend.routes import backtests as backtests_routes
from paper_trading_ui.backend.routes import logs as logs_routes
from trading.services.accounts_service import create_account
from trading.domain import AccountAlreadyExistsError
from trading.database import db
from trading.models import AccountConfig


def _create_test_account(
    conn,
    name: str,
    strategy: str = "trend_v1",
    initial_cash: float = 5000.0,
    benchmark: str = "SPY",
    **kwargs,
) -> None:
    create_account(conn, name, strategy, initial_cash, benchmark, config=AccountConfig(**kwargs) if kwargs else None)


def _create_backtest_run_for_account(conn, account_name: str, run_name: str = "run-abc") -> None:
    account = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    assert account is not None
    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(account["id"]),
            run_name,
            "2026-01-01",
            "2026-01-31",
            utc_now_iso(),
            5.0,
            0.0,
            "trading/config/trade_universe.txt",
        ),
    )
    conn.commit()


def _seed_account(account_name: str) -> None:
    conn = db.ensure_db()
    try:
        _create_test_account(conn, account_name)
    finally:
        conn.close()


class TestHealthAndAccountsRoutes:
    def test_health_endpoint_returns_ok(self, api_client: TestClient) -> None:
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_accounts_endpoint_includes_virtual_test_account(self, api_client: TestClient) -> None:
        _seed_account("acct_listed")

        response = api_client.get("/api/accounts")
        assert response.status_code == 200

        accounts = response.json()["accounts"]
        names = [item["name"] for item in accounts]
        assert "acct_listed" in names
        assert TEST_ACCOUNT_NAME in names
        listed = next(item for item in accounts if item["name"] == "acct_listed")
        assert "instrumentMode" in listed
        assert "optionMinDte" not in listed
        assert "rotationOverlayWatchlist" not in listed

    def test_account_detail_virtual_test_account_branch(self, api_client: TestClient) -> None:
        response = api_client.get(f"/api/accounts/{TEST_ACCOUNT_NAME}")
        assert response.status_code == 200

        payload = response.json()
        assert payload["account"]["name"] == TEST_ACCOUNT_NAME
        assert isinstance(payload["trades"], list)
        assert isinstance(payload["snapshots"], list)


class TestActionsRoutes:
    def test_snapshot_endpoint_virtual_account(self, api_client: TestClient) -> None:
        response = api_client.post(f"/api/actions/snapshot/{TEST_ACCOUNT_NAME}")
        assert response.status_code == 200
        assert "virtual" in response.json()["message"].lower()

    def test_snapshot_endpoint_real_account_saves_snapshot(self, api_client: TestClient) -> None:
        _seed_account("acct_snapshot")

        response = api_client.post("/api/actions/snapshot/acct_snapshot")
        assert response.status_code == 200

        conn = db.ensure_db()
        try:
            account = conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_snapshot",)).fetchone()
            assert account is not None
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM equity_snapshots WHERE account_id = ?",
                (int(account["id"]),),
            ).fetchone()["n"]
        finally:
            conn.close()

        assert int(count) == 1

    def test_snapshot_all_endpoint_includes_virtual_name(self, api_client: TestClient) -> None:
        conn = db.ensure_db()
        try:
            _create_test_account(conn, "acct_all_a")
            _create_test_account(conn, "acct_all_b")
        finally:
            conn.close()

        response = api_client.post("/api/actions/snapshot-all")
        assert response.status_code == 200

        snapshotted = response.json()["snapshotted"]
        assert "acct_all_a" in snapshotted
        assert "acct_all_b" in snapshotted
        assert TEST_ACCOUNT_NAME in snapshotted


class TestAdminRoutes:
    def test_admin_delete_requires_confirmation(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": "acct_any", "confirm": False},
        )
        assert response.status_code == 400
        assert "explicit confirmation" in response.json()["detail"]

    def test_admin_delete_rejects_virtual_test_account(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/api/admin/accounts/delete",
            json={"accountName": TEST_ACCOUNT_NAME, "confirm": True},
        )
        assert response.status_code == 400
        assert "cannot be deleted" in response.json()["detail"]

    def test_admin_create_account_handles_value_error(self, monkeypatch, api_client: TestClient) -> None:
        def _raise_value_error(*_args, **_kwargs):
            raise ValueError("bad payload")

        monkeypatch.setattr(admin_routes, "create_account_with_rotation", _raise_value_error)

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

    def test_admin_create_account_handles_duplicate_record(self, monkeypatch, api_client: TestClient) -> None:
        def _raise_duplicate(*_args, **_kwargs):
            raise ValueError("Account create failed: already exists")

        monkeypatch.setattr(admin_routes, "create_account_with_rotation", _raise_duplicate)

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

    def test_admin_exports_endpoints_delegate_to_services(self, monkeypatch, api_client: TestClient) -> None:
        monkeypatch.setattr(admin_routes, "list_csv_exports", lambda: {"exports": [{"name": "db_csv_1", "files": []}]})

        def _preview(export_name: str, file_name: str, _limit: int) -> dict[str, object]:
            return {
                "exportName": export_name,
                "fileName": file_name,
                "returned": 0,
                "header": [],
                "rows": [],
                "truncated": False,
            }

        monkeypatch.setattr(admin_routes, "preview_csv_export", _preview)

        exports_response = api_client.get("/api/admin/exports/csv")
        assert exports_response.status_code == 200
        assert exports_response.json()["exports"][0]["name"] == "db_csv_1"

        preview_response = api_client.get(
            "/api/admin/exports/csv/preview",
            params={"exportName": "db_csv_1", "fileName": "accounts.csv", "limit": 10},
        )
        assert preview_response.status_code == 200
        assert preview_response.json()["exportName"] == "db_csv_1"


class TestBacktestsRoutes:
    def test_backtest_runs_endpoint_returns_rows(self, api_client: TestClient) -> None:
        conn = db.ensure_db()
        try:
            _create_test_account(conn, "acct_runs")
            _create_backtest_run_for_account(conn, "acct_runs", run_name="run-abc")
        finally:
            conn.close()

        response = api_client.get("/api/backtests/runs", params={"limit": 1})
        assert response.status_code == 200
        assert len(response.json()["runs"]) == 1
        assert response.json()["runs"][0]["runName"] == "run-abc"

    def test_latest_backtest_endpoint_missing_account_returns_404(self, api_client: TestClient) -> None:
        response = api_client.get("/api/backtests/latest/no_such_account")
        assert response.status_code == 404

    def test_backtest_run_report_endpoint_not_found(self, monkeypatch, api_client: TestClient) -> None:
        def _raise_not_found(_conn, _run_id):
            raise ValueError("run not found")

        monkeypatch.setattr(backtests_routes, "backtest_report_full", _raise_not_found)

        response = api_client.get("/api/backtests/runs/999")
        assert response.status_code == 404
        assert "run not found" in response.json()["detail"]

    def test_backtest_run_report_endpoint_success(self, monkeypatch, api_client: TestClient) -> None:
        monkeypatch.setattr(
            backtests_routes,
            "backtest_report_full",
            lambda _conn, _run_id: SimpleNamespace(to_payload=lambda: {"runId": 77, "summary": {"x": 1}}),
        )

        response = api_client.get("/api/backtests/runs/77")
        assert response.status_code == 200
        assert response.json()["runId"] == 77

    def test_backtest_run_endpoint_value_error(self, monkeypatch, api_client: TestClient) -> None:
        _seed_account("acct_run_err")

        def _raise_bad_config(_conn, _cfg):
            raise ValueError("bad config")

        monkeypatch.setattr(backtests_routes, "run_backtest", _raise_bad_config)

        response = api_client.post(
            "/api/backtests/run",
            json={
                "account": "acct_run_err",
                "tickersFile": "trading/config/trade_universe.txt",
                "start": "2026-01-01",
                "end": "2026-01-31",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "bad config"

    def test_backtest_preflight_endpoint_file_not_found(self, monkeypatch, api_client: TestClient) -> None:
        _seed_account("acct_preflight_missing_file")

        def _raise_missing_file(_conn, _cfg):
            raise FileNotFoundError("tickers file missing")

        monkeypatch.setattr(backtests_routes, "preview_backtest_warnings", _raise_missing_file)

        response = api_client.post(
            "/api/backtests/preflight",
            json={
                "account": "acct_preflight_missing_file",
                "tickersFile": "missing.txt",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "tickers file missing"

    def test_walk_forward_endpoint_value_error(self, monkeypatch, api_client: TestClient) -> None:
        _seed_account("acct_wf_err")

        def _raise_wf_error(_conn, _cfg):
            raise ValueError("wf bad config")

        monkeypatch.setattr(backtests_routes, "run_walk_forward_backtest", _raise_wf_error)

        response = api_client.post(
            "/api/backtests/walk-forward",
            json={
                "account": "acct_wf_err",
                "tickersFile": "trading/config/trade_universe.txt",
                "testMonths": 1,
                "stepMonths": 1,
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "wf bad config"


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
