from __future__ import annotations

import sqlite3
from collections.abc import Callable

from fastapi.testclient import TestClient

from trading.services.accounts import get_account


class TestActionsRoutes:
    def test_snapshot_endpoint_real_account_saves_snapshot(
        self,
        api_client: TestClient,
        api_conn: sqlite3.Connection,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_snapshot")

        response = api_client.post("/api/actions/snapshot/acct_snapshot")
        assert response.status_code == 200

        account = get_account(api_conn, "acct_snapshot")
        count = api_conn.execute(
            "SELECT COUNT(*) AS n FROM equity_snapshots s JOIN books b ON b.id = s.book_id WHERE b.account_id = ?",
            (account["id"],),
        ).fetchone()["n"]
        assert int(count) == 1

    def test_snapshot_endpoint_unknown_account_returns_404(self, api_client: TestClient) -> None:
        response = api_client.post("/api/actions/snapshot/no_such_account")
        assert response.status_code == 404

    def test_snapshot_all_endpoint_lists_seeded_accounts(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_all_a")
        seed_account("acct_all_b")

        response = api_client.post("/api/actions/snapshot-all")
        assert response.status_code == 200

        snapshotted = response.json()["snapshotted"]
        assert "acct_all_a" in snapshotted
        assert "acct_all_b" in snapshotted
