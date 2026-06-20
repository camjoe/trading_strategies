from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

_BACKTEST_REPORT_FULL = "paper_trading_web.backend.routes.backtests.backtest_report_full"
_RUN_BACKTEST = "paper_trading_web.backend.routes.backtests.run_backtest"
_PREVIEW_BACKTEST_WARNINGS = "paper_trading_web.backend.routes.backtests.preview_backtest_warnings"
_RUN_WALK_FORWARD = "paper_trading_web.backend.routes.backtests.run_walk_forward_backtest"


class TestBacktestsRoutes:
    def test_backtest_runs_endpoint_returns_rows(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
        seed_backtest_run: Callable[[str, str], None],
    ) -> None:
        seed_account("acct_runs")
        seed_backtest_run("acct_runs", "run-abc")

        response = api_client.get("/api/backtests/runs", params={"limit": 1})
        assert response.status_code == 200
        assert len(response.json()["runs"]) == 1
        assert response.json()["runs"][0]["runName"] == "run-abc"

    def test_latest_backtest_endpoint_missing_account_returns_404(self, api_client: TestClient) -> None:
        response = api_client.get("/api/backtests/latest/no_such_account")
        assert response.status_code == 404

    def test_latest_backtest_endpoint_returns_none_when_missing(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_api_empty", initial_cash=10000.0)

        response = api_client.get("/api/backtests/latest/acct_api_empty")
        assert response.status_code == 200
        payload = response.json()
        assert payload["accountName"] == "acct_api_empty"
        assert payload["latestRun"] is None

    def test_backtest_run_report_endpoint_not_found(self, api_client: TestClient) -> None:
        report_mock = Mock(side_effect=ValueError("run not found"))
        with patch(_BACKTEST_REPORT_FULL, report_mock):
            response = api_client.get("/api/backtests/runs/999")
        assert response.status_code == 404
        assert "run not found" in response.json()["detail"]
        report_mock.assert_called_once()

    def test_backtest_run_report_endpoint_success(self, api_client: TestClient) -> None:
        report_mock = Mock(
            return_value=SimpleNamespace(to_payload=lambda: {"runId": 77, "summary": {"x": 1}}),
        )
        with patch(_BACKTEST_REPORT_FULL, report_mock):
            response = api_client.get("/api/backtests/runs/77")
        assert response.status_code == 200
        assert response.json()["runId"] == 77
        report_mock.assert_called_once()

    def test_backtest_run_endpoint_value_error(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_run_err")

        run_mock = Mock(side_effect=ValueError("bad config"))
        with patch(_RUN_BACKTEST, run_mock):
            response = api_client.post(
                "/api/backtests/run",
                json={
                    "account": "acct_run_err",
                    "tickersFile": "src/infrastructure/config/trade_universe.txt",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "bad config"
        run_mock.assert_called_once()

    def test_backtest_preflight_endpoint_file_not_found(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_preflight_missing_file")

        warnings_mock = Mock(side_effect=FileNotFoundError("tickers file missing"))
        with patch(_PREVIEW_BACKTEST_WARNINGS, warnings_mock):
            response = api_client.post(
                "/api/backtests/preflight",
                json={
                    "account": "acct_preflight_missing_file",
                    "tickersFile": "missing.txt",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "tickers file missing"
        warnings_mock.assert_called_once()

    def test_backtest_preflight_returns_financial_warnings(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account(
            "acct_api_leaps",
            instrument_mode="leaps",
            option_strike_offset_pct=5.0,
            option_min_dte=120,
            option_max_dte=365,
            option_type="call",
        )

        response = api_client.post(
            "/api/backtests/preflight",
            json={
                "account": "acct_api_leaps",
                "tickersFile": "src/infrastructure/config/trade_universe.txt",
                "start": "2026-01-01",
                "end": "2026-03-01",
                "allowApproximateLeaps": False,
            },
        )
        assert response.status_code == 200
        warnings = response.json()["warnings"]
        assert any("LEAPs mode is approximated" in warning for warning in warnings)
        assert any("opt-in was not enabled" in warning for warning in warnings)

    def test_backtest_preflight_rejects_start_and_lookback_conflict(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_api_conflict")
        response = api_client.post(
            "/api/backtests/preflight",
            json={
                "account": "acct_api_conflict",
                "tickersFile": "src/infrastructure/config/trade_universe.txt",
                "start": "2026-01-01",
                "lookbackMonths": 1,
            },
        )
        assert response.status_code == 400
        assert "Use either --start or --lookback-months" in response.json()["detail"]

    def test_walk_forward_endpoint_value_error(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_wf_err")

        walk_forward_mock = Mock(side_effect=ValueError("wf bad config"))
        with patch(_RUN_WALK_FORWARD, walk_forward_mock):
            response = api_client.post(
                "/api/backtests/walk-forward",
                json={
                    "account": "acct_wf_err",
                    "tickersFile": "src/infrastructure/config/trade_universe.txt",
                    "testMonths": 1,
                    "stepMonths": 1,
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "wf bad config"
        walk_forward_mock.assert_called_once()

