from __future__ import annotations

from trading.services.accounts_service import create_account
from trading.repositories.rotation_repository import update_account_rotation_state


def _account_id(conn, name: str = "rot_acct") -> int:
    create_account(conn, name, "Trend", 5000.0, "SPY")
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


class TestUpdateAccountRotationState:
    def test_updates_all_rotation_fields(self, conn) -> None:
        acct_id = _account_id(conn)
        update_account_rotation_state(
            conn,
            account_id=acct_id,
            strategy="meanrev",
            rotation_active_index=1,
            rotation_active_strategy="meanrev",
            rotation_last_at="2026-03-01T00:00:00Z",
        )
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
        assert row["strategy"] == "meanrev"
        assert int(row["rotation_active_index"]) == 1
        assert row["rotation_active_strategy"] == "meanrev"
        assert row["rotation_last_at"] == "2026-03-01T00:00:00Z"

    def test_does_not_affect_other_accounts(self, conn) -> None:
        acct_a = _account_id(conn, "rot_a")
        acct_b = _account_id(conn, "rot_b")
        original_strategy = conn.execute(
            "SELECT strategy FROM accounts WHERE id = ?", (acct_b,)
        ).fetchone()["strategy"]

        update_account_rotation_state(
            conn,
            account_id=acct_a,
            strategy="newstrat",
            rotation_active_index=0,
            rotation_active_strategy="newstrat",
            rotation_last_at="2026-03-30T00:00:00Z",
        )

        unchanged = conn.execute(
            "SELECT strategy FROM accounts WHERE id = ?", (acct_b,)
        ).fetchone()
        assert unchanged["strategy"] == original_strategy

    def test_can_be_called_multiple_times_overwriting(self, conn) -> None:
        acct_id = _account_id(conn)
        for i, strat in enumerate(["alpha", "beta", "gamma"]):
            update_account_rotation_state(
                conn,
                account_id=acct_id,
                strategy=strat,
                rotation_active_index=i,
                rotation_active_strategy=strat,
                rotation_last_at=f"2026-03-{i + 1:02d}T00:00:00Z",
            )
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
        assert row["strategy"] == "gamma"
        assert int(row["rotation_active_index"]) == 2
