from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from trading.database.db_init import ensure_db


class TestActionsRoutes:
    def test_snapshot_endpoint_real_account_saves_snapshot(
        self,
        api_client: TestClient,
        seed_account: Callable[..., None],
    ) -> None:
        seed_account("acct_snapshot")

        response = api_client.post("/api/actions/snapshot/acct_snapshot")
        assert response.status_code == 200

        conn = ensure_db()
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
