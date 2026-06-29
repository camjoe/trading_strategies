from __future__ import annotations

from trading.repositories.accounts import AccountRepository
from trading.repositories.rotation import RotationEpisodeRepository
from tests.support.repositories import insert_repository_account


def _account_id(conn, name: str = "rot_acct") -> int:
    return insert_repository_account(conn, name=name)


class TestUpdateAccountRotationState:
    def test_updates_all_rotation_fields(self, conn) -> None:
        acct_id = _account_id(conn)
        AccountRepository(conn).update_rotation_state(
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
        original_strategy = conn.execute("SELECT strategy FROM accounts WHERE id = ?", (acct_b,)).fetchone()[
            "strategy"
        ]

        AccountRepository(conn).update_rotation_state(
            account_id=acct_a,
            strategy="newstrat",
            rotation_active_index=0,
            rotation_active_strategy="newstrat",
            rotation_last_at="2026-03-30T00:00:00Z",
        )

        unchanged = conn.execute("SELECT strategy FROM accounts WHERE id = ?", (acct_b,)).fetchone()
        assert unchanged["strategy"] == original_strategy

    def test_can_be_called_multiple_times_overwriting(self, conn) -> None:
        acct_id = _account_id(conn)
        for i, strat in enumerate(["alpha", "beta", "gamma"]):
            AccountRepository(conn).update_rotation_state(
                account_id=acct_id,
                strategy=strat,
                rotation_active_index=i,
                rotation_active_strategy=strat,
                rotation_last_at=f"2026-03-{i + 1:02d}T00:00:00Z",
            )
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone()
        assert row["strategy"] == "gamma"
        assert int(row["rotation_active_index"]) == 2


class TestRotationEpisodes:
    def test_insert_fetch_and_close_rotation_episode(self, conn) -> None:
        acct_id = _account_id(conn, "rot_episode")
        repo = RotationEpisodeRepository(conn)
        repo.insert(
            account_id=acct_id,
            strategy_name="trend",
            started_at="2026-03-01T00:00:00Z",
            starting_equity=1000.0,
            starting_realized_pnl=10.0,
        )

        open_row = repo.fetch_open(account_id=acct_id)
        assert open_row is not None
        assert open_row["strategy_name"] == "trend"

        repo.close_episode(
            episode_id=int(open_row["id"]),
            ended_at="2026-03-10T00:00:00Z",
            ending_equity=1120.0,
            ending_realized_pnl=25.0,
            realized_pnl_delta=15.0,
            snapshot_count=3,
        )

        closed_rows = repo.fetch_closed(
            account_id=acct_id,
            strategy_names=["trend"],
            start_iso="2026-03-01T00:00:00Z",
            end_iso="2026-03-31T00:00:00Z",
        )
        assert len(closed_rows) == 1
        assert closed_rows[0]["ending_equity"] == 1120.0
        assert closed_rows[0]["realized_pnl_delta"] == 15.0
        assert int(closed_rows[0]["snapshot_count"]) == 3

    def test_fetch_closed_rotation_episodes_returns_empty_for_empty_strategy_filter(self, conn) -> None:
        acct_id = _account_id(conn, "rot_empty_filter")

        assert (
            RotationEpisodeRepository(conn).fetch_closed(
                account_id=acct_id,
                strategy_names=[],
                start_iso="2026-03-01T00:00:00Z",
                end_iso="2026-03-31T00:00:00Z",
            )
            == []
        )

    def test_fetch_latest_closed_rotation_episode_returns_most_recent_match(self, conn) -> None:
        acct_id = _account_id(conn, "rot_latest")
        repo = RotationEpisodeRepository(conn)

        assert repo.fetch_latest_closed(account_id=acct_id, strategy_name="trend") is None

        for started_at, ended_at, ending_equity in [
            ("2026-03-01T00:00:00Z", "2026-03-05T00:00:00Z", 1010.0),
            ("2026-03-06T00:00:00Z", "2026-03-09T00:00:00Z", 1030.0),
        ]:
            repo.insert(
                account_id=acct_id,
                strategy_name="trend",
                started_at=started_at,
                starting_equity=1000.0,
                starting_realized_pnl=0.0,
            )
            open_row = repo.fetch_open(account_id=acct_id)
            assert open_row is not None
            repo.close_episode(
                episode_id=int(open_row["id"]),
                ended_at=ended_at,
                ending_equity=ending_equity,
                ending_realized_pnl=5.0,
                realized_pnl_delta=5.0,
                snapshot_count=2,
            )

        latest = repo.fetch_latest_closed(account_id=acct_id, strategy_name="trend")

        assert latest is not None
        assert latest["ended_at"] == "2026-03-09T00:00:00Z"
        assert float(latest["ending_equity"]) == 1030.0
