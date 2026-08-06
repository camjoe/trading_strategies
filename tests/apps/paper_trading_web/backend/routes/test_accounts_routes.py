from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from paper_trading_web.backend.routes.accounts import ROTATION_POLICY_REQUEST_NAMES
from paper_trading_web.backend.schemas.accounts import RotationPolicyRequest

from trading.services.parameters.mutations import ROTATION_POLICY_FIELDS


def test_account_config_options_endpoint_returns_canonical_choices(api_client: TestClient) -> None:
    response = api_client.get("/api/accounts/config/options")
    assert response.status_code == 200

    payload = response.json()
    assert payload["goalPeriods"] == ["monthly", "weekly", "quarterly", "yearly"]
    assert payload["riskPolicies"] == ["none", "fixed_stop", "take_profit", "stop_and_target"]
    assert payload["instrumentModes"] == ["equity", "leaps"]
    assert payload["optionTypes"] == ["call", "put", "both"]
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


def test_account_detail_known_account(api_client: TestClient, seed_account: Callable[..., None]) -> None:
    seed_account("acct_detail")

    response = api_client.get("/api/accounts/acct_detail")
    assert response.status_code == 200

    payload = response.json()
    assert payload["account"]["name"] == "acct_detail"
    assert isinstance(payload["trades"], list)
    assert isinstance(payload["snapshots"], list)
    assert len(payload["books"]) == 1
    assert payload["books"][0]["isDefault"] is True
    assert payload["books"][0]["strategy"] == "trend_v1"


def test_book_params_endpoint_updates_named_book(
    api_client: TestClient,
    api_conn: sqlite3.Connection,
    seed_account: Callable[..., None],
) -> None:
    seed_account("acct_book_params")
    book_name = api_conn.execute(
        """
        SELECT b.name
        FROM books b
        JOIN accounts a ON a.id = b.account_id
        WHERE a.name = ? AND b.is_default = 1
        """,
        ("acct_book_params",),
    ).fetchone()["name"]

    response = api_client.patch(
        f"/api/accounts/acct_book_params/books/{book_name}/params",
        json={
            "strategy": "mean_reversion",
            "riskPolicy": "fixed_stop",
            "tradeUniverses": ["default", "growth"],
            "rotation": {
                "enabled": True,
                "schedule": ["trend", "mean_reversion"],
                "lookbackDays": 30,
            },
            "rotationPolicy": {
                "minTradesInWindow": 8,
                "cooldownDays": 14,
            },
        },
    )
    assert response.status_code == 200

    detail = api_client.get("/api/accounts/acct_book_params").json()
    book = detail["books"][0]
    assert book["strategy"] == "mean_reversion"
    assert book["riskPolicy"] == "fixed_stop"
    assert book["tradeUniverses"] == ["default", "growth"]
    assert book["rotation"]["lookbackDays"] == 30
    assert book["rotationPolicy"]["minTradesInWindow"] == 8
    assert book["rotationPolicy"]["cooldownDays"] == 14


def test_book_params_endpoint_rejects_unknown_trade_universe(
    api_client: TestClient,
    api_conn: sqlite3.Connection,
    seed_account: Callable[..., None],
) -> None:
    """An unresolvable universe name must fail the PATCH, not persist and break the next run."""
    seed_account("acct_bad_universe")
    book_name = api_conn.execute(
        """
        SELECT b.name
        FROM books b
        JOIN accounts a ON a.id = b.account_id
        WHERE a.name = ? AND b.is_default = 1
        """,
        ("acct_bad_universe",),
    ).fetchone()["name"]

    response = api_client.patch(
        f"/api/accounts/acct_bad_universe/books/{book_name}/params",
        json={"tradeUniverses": ["default", "no_such_universe"]},
    )

    assert response.status_code == 422
    assert "no_such_universe" in response.json()["detail"]


def test_account_detail_exposes_latest_backtest_summary(
    api_client: TestClient,
    seed_account: Callable[..., None],
    seed_backtest_run: Callable[[str, str], None],
) -> None:
    seed_account("acct_detail_latest")
    seed_backtest_run("acct_detail_latest", "latest-run")

    response = api_client.get("/api/accounts/acct_detail_latest")
    assert response.status_code == 200

    payload = response.json()
    assert payload["account"]["brokerType"] == "paper"
    latest = payload["latestBacktest"]
    assert latest is not None
    assert latest["accountName"] == "acct_detail_latest"
    assert latest["runName"] == "latest-run"


def test_accounts_compare_lists_visible_accounts(
    api_client: TestClient,
    seed_account: Callable[..., None],
) -> None:
    seed_account("acct_compare_visible")

    response = api_client.get("/api/accounts/compare")
    assert response.status_code == 200

    names = [item["name"] for item in response.json()["accounts"]]
    assert "acct_compare_visible" in names


def test_accounts_compare_includes_evaluation_summary(
    api_client: TestClient,
    seed_account: Callable[..., None],
) -> None:
    seed_account("acct_compare_evaluation")

    response = api_client.get("/api/accounts/compare")
    assert response.status_code == 200

    account = next(item for item in response.json()["accounts"] if item["name"] == "acct_compare_evaluation")
    assert account["evaluation"]["blendedScore"] is None
    assert account["evaluation"]["overallConfidence"] == pytest.approx(0.0)
    assert account["evaluation"]["backtestConfidence"] == pytest.approx(0.0)
    assert account["evaluation"]["paperLiveConfidence"] == pytest.approx(0.0)
    assert "missing_backtest_evidence" in account["evaluation"]["dataGaps"]


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
                "rotation": {
                    "enabled": True,
                    "schedule": ["trend", "ma_crossover", "mean_reversion"],
                    "lookbackDays": 30,
                },
            },
        )
        assert resp.status_code == 200

        detail = api_client.get("/api/accounts/acct_params_rotation").json()
        account = detail["account"]
        assert account["rotation"] == {
            "enabled": True,
            "schedule": ["trend", "ma_crossover", "mean_reversion"],
            "lookbackDays": 30,
        }


def _camel_to_snake(name: str) -> str:
    return "".join(f"_{char.lower()}" if char.isupper() else char for char in name)


class TestRotationPolicyContract:
    """The API's rotation-policy surface must expose exactly the domain's knobs.

    Four parallel lists describe the same policy: ``ROTATION_POLICY_FIELDS``
    (the owning edit surface), the GET payload, the request schema, and the
    write mapping. They have drifted in both directions before — a knob dropped
    from the domain was left behind in the read path and raised AttributeError,
    and a knob added to the domain was never exposed, leaving a live scoring
    weight silently un-editable. These assertions fail on either kind of drift.
    """

    def test_get_payload_exposes_every_policy_field(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_policy_contract")

        detail = api_client.get("/api/accounts/acct_policy_contract").json()
        payload_fields = {_camel_to_snake(name) for name in detail["books"][0]["rotationPolicy"]}

        assert payload_fields == set(ROTATION_POLICY_FIELDS)

    def test_request_schema_accepts_every_policy_field(self) -> None:
        schema_fields = {_camel_to_snake(name) for name in RotationPolicyRequest.model_fields}

        assert schema_fields == set(ROTATION_POLICY_FIELDS)

    def test_write_mapping_covers_every_policy_field(self) -> None:
        assert set(ROTATION_POLICY_REQUEST_NAMES.values()) == set(ROTATION_POLICY_FIELDS)
        # Every request name must also convert cleanly, so the schema and the
        # mapping cannot disagree about casing.
        assert all(_camel_to_snake(name) == field for name, field in ROTATION_POLICY_REQUEST_NAMES.items())
