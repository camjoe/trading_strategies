from __future__ import annotations

import pytest

from trading.repositories.rotation_decisions import RotationDecisionRepository
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


def _account_id(conn, name: str = "rot_dec_acct") -> int:
    return insert_repository_account(conn, name=name)


def _sleeve_id(conn, account_id: int) -> int:
    return insert_test_sleeve(conn, account_id=account_id)


def _insert(
    conn,
    *,
    sleeve_id: int,
    decision_time: str,
    rotation_action: str = "hold",
    incumbent_strategy: str = "trend",
    challenger_strategy: str = "meanrev",
    selected_strategy: str = "trend",
    decision_reason: str | None = "threshold_not_met",
) -> int:
    return RotationDecisionRepository(conn).insert(
        sleeve_id=sleeve_id,
        decision_time=decision_time,
        incumbent_strategy=incumbent_strategy,
        challenger_strategy=challenger_strategy,
        selected_strategy=selected_strategy,
        rotation_action=rotation_action,
        cooldown_active=0,
        score_components_json="{}",
        gate_results_json="{}",
        decision_reason=decision_reason,
        config_version=None,
        param_set_id=None,
        created_at=decision_time,
    )


class TestInsert:
    def test_returns_positive_id(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        row_id = _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T10:00:00Z")
        assert row_id > 0

    def test_raises_when_lastrowid_missing(self) -> None:
        class _Cursor:
            lastrowid = None
            def fetchone(self): return None
            def fetchall(self): return []

        class _Conn:
            def execute(self, *_a, **_kw): return _Cursor()
            def commit(self): pass

        with pytest.raises(ValueError, match="Expected rotation_decisions id after insert"):
            RotationDecisionRepository(_Conn()).insert(
                sleeve_id=1, decision_time="2026-01-01T00:00:00Z",
                incumbent_strategy=None, challenger_strategy=None,
                selected_strategy=None, rotation_action="hold",
                cooldown_active=0, score_components_json="{}", gate_results_json="{}",
                decision_reason=None, config_version=None, param_set_id=None,
                created_at="2026-01-01T00:00:00Z",
            )


class TestFetchLatest:
    def test_returns_none_when_no_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        assert RotationDecisionRepository(conn).fetch_latest(sleeve_id=slv_id) is None

    def test_returns_most_recent_by_decision_time(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T09:00:00Z", decision_reason="first")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T11:00:00Z", decision_reason="latest")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T10:00:00Z", decision_reason="middle")
        row = RotationDecisionRepository(conn).fetch_latest(sleeve_id=slv_id)
        assert row is not None
        assert row["decision_reason"] == "latest"

    def test_isolated_per_sleeve(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_a = _sleeve_id(conn, acct_id)
        slv_b = insert_test_sleeve(conn, account_id=acct_id, name="sleeve_b")
        _insert(conn, sleeve_id=slv_a, decision_time="2026-01-01T10:00:00Z", decision_reason="for_a")
        assert RotationDecisionRepository(conn).fetch_latest(sleeve_id=slv_b) is None


class TestFetchForSleeve:
    def test_returns_empty_list_when_no_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        assert RotationDecisionRepository(conn).fetch_for_sleeve(sleeve_id=slv_id, limit=10) == []

    def test_limit_is_respected(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        for hour in range(5):
            _insert(conn, sleeve_id=slv_id, decision_time=f"2026-01-01T{hour:02d}:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve(sleeve_id=slv_id, limit=3)
        assert len(rows) == 3

    def test_ordered_by_decision_time_desc(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T09:00:00Z")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T11:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve(sleeve_id=slv_id, limit=10)
        times = [r["decision_time"] for r in rows]
        assert times == sorted(times, reverse=True)


class TestFetchForSleeveOnDate:
    def test_returns_only_rows_on_given_date(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T23:59:00Z", decision_reason="before")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T09:00:00Z", decision_reason="on_date")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-03T00:00:00Z", decision_reason="after")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(
            sleeve_id=slv_id, report_date="2026-01-02"
        )
        assert len(rows) == 1
        assert rows[0]["decision_reason"] == "on_date"

    def test_date_boundary_is_exclusive_at_end(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T23:59:59Z", decision_reason="last_second")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-03T00:00:00Z", decision_reason="next_day")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(
            sleeve_id=slv_id, report_date="2026-01-02"
        )
        assert len(rows) == 1
        assert rows[0]["decision_reason"] == "last_second"

    def test_ordered_by_decision_time_asc(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T11:00:00Z")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T09:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(
            sleeve_id=slv_id, report_date="2026-01-02"
        )
        times = [r["decision_time"] for r in rows]
        assert times == sorted(times)


class TestFetchLatestRotateAction:
    def test_returns_none_when_no_rotate_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T10:00:00Z", rotation_action="hold")
        assert RotationDecisionRepository(conn).fetch_latest_rotate_action(sleeve_id=slv_id) is None

    def test_returns_most_recent_rotate_ignoring_holds(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T09:00:00Z", rotation_action="rotate", decision_reason="first_rotate")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T10:00:00Z", rotation_action="hold")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T11:00:00Z", rotation_action="rotate", decision_reason="latest_rotate")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T12:00:00Z", rotation_action="hold")
        row = RotationDecisionRepository(conn).fetch_latest_rotate_action(sleeve_id=slv_id)
        assert row is not None
        assert row["decision_reason"] == "latest_rotate"
