import pytest

from tests.support.seed.db import ACCT_TREND
from trading.services.accounts import (
    create_account,
    find_account,
    get_account,
    list_account_names,
    list_account_records,
)


class TestAccountQueries:
    # Reads against pre-seeded accounts — no writes, seeded_conn safe.
    def test_get_account_not_found_raises(self, seeded_conn) -> None:
        with pytest.raises(ValueError, match="Account 'missing' not found"):
            get_account(seeded_conn, "missing")

    def test_find_account_strips_whitespace_and_returns_row(self, seeded_conn) -> None:
        account = find_account(seeded_conn, f"  {ACCT_TREND}  ")

        assert account is not None
        assert account["name"] == ACCT_TREND
        assert find_account(seeded_conn, "no_such_account") is None

    # Exact-list assertion on a known set — uses isolated conn to avoid noise
    # from the shared seeded DB.
    def test_list_account_records_returns_all_accounts(self, conn) -> None:
        create_account(conn, "acct_alpha", "Trend", 1000.0, "SPY")
        create_account(conn, "acct_beta", "Trend", 1000.0, "SPY")
        rows = list_account_records(conn)
        names = [row["name"] for row in rows]

        assert names == ["acct_alpha", "acct_beta"]
        assert list_account_names(conn) == ["acct_alpha", "acct_beta"]


# ---------------------------------------------------------------------------
# Guard validation paths (previously uncovered)
# ---------------------------------------------------------------------------


class TestAccountQueryGuards:
    def test_find_account_empty_name_raises(self, conn) -> None:
        from trading.services.accounts.queries import find_account as _find_account

        with pytest.raises(ValueError, match="cannot be empty"):
            _find_account(conn, "   ")

    def test_get_latest_snapshot_invalid_id_raises(self, conn) -> None:
        from trading.services.accounts.queries import get_latest_account_snapshot

        with pytest.raises(ValueError, match="must be positive"):
            get_latest_account_snapshot(conn, 0)

    def test_list_account_snapshots_invalid_id_raises(self, conn) -> None:
        from trading.services.accounts.queries import list_account_snapshots

        with pytest.raises(ValueError, match="must be positive"):
            list_account_snapshots(conn, -1, limit=10)

    def test_list_account_snapshots_invalid_limit_raises(self, conn) -> None:
        from trading.services.accounts import create_account
        from trading.services.accounts.queries import list_account_snapshots

        create_account(conn, "snap_acct", "Trend", 1000.0, "SPY")
        acct = conn.execute("SELECT id FROM accounts WHERE name='snap_acct'").fetchone()
        with pytest.raises(ValueError, match="limit must be positive"):
            list_account_snapshots(conn, acct["id"], limit=0)

    def test_load_runtime_eligible_account_names_returns_list(self, conn) -> None:
        # conn sets the global backend to a test DB so load_runtime_eligible_account_names
        # does not hit the real on-disk database.
        from trading.services.accounts.runtime_loader import load_runtime_eligible_account_names

        result = load_runtime_eligible_account_names()
        assert isinstance(result, list)
