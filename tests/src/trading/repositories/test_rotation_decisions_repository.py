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
            def __init__(self, *, lastrowid=None, row=None) -> None:
                self.lastrowid = lastrowid
                self.rowcount = 1
                self._row = row

            def fetchone(self):
                return self._row

            def fetchall(self):
                return []

        sleeve_row = {
            "account_id": 1,
            "name": "core",
            "start_equity": 100.0,
            "current_cash": 100.0,
            "current_equity": 100.0,
            "created_at": "2026-01-01T00:00:00Z",
        }

        class _Conn:
            def __init__(self) -> None:
                # sleeve lookup, books lookup miss, bridging-book insert, decision insert
                self._cursors = [
                    _Cursor(row=sleeve_row),
                    _Cursor(row=None),
                    _Cursor(lastrowid=5),
                    _Cursor(lastrowid=None),
                ]

            def execute(self, *_a, **_kw):
                return self._cursors.pop(0)

            def commit(self):
                pass

        with pytest.raises(ValueError, match="Expected rotation_decisions id after insert"):
            RotationDecisionRepository(_Conn()).insert(
                sleeve_id=1,
                decision_time="2026-01-01T00:00:00Z",
                incumbent_strategy=None,
                challenger_strategy=None,
                selected_strategy=None,
                rotation_action="hold",
                cooldown_active=0,
                score_components_json="{}",
                gate_results_json="{}",
                decision_reason=None,
                config_version=None,
                param_set_id=None,
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
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(sleeve_id=slv_id, report_date="2026-01-02")
        assert len(rows) == 1
        assert rows[0]["decision_reason"] == "on_date"

    def test_date_boundary_is_exclusive_at_end(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T23:59:59Z", decision_reason="last_second")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-03T00:00:00Z", decision_reason="next_day")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(sleeve_id=slv_id, report_date="2026-01-02")
        assert len(rows) == 1
        assert rows[0]["decision_reason"] == "last_second"

    def test_ordered_by_decision_time_asc(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_id = _sleeve_id(conn, acct_id)
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T11:00:00Z")
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-02T09:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_sleeve_on_date(sleeve_id=slv_id, report_date="2026-01-02")
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
        _insert(
            conn,
            sleeve_id=slv_id,
            decision_time="2026-01-01T09:00:00Z",
            rotation_action="rotate",
            decision_reason="first_rotate",
        )
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T10:00:00Z", rotation_action="hold")
        _insert(
            conn,
            sleeve_id=slv_id,
            decision_time="2026-01-01T11:00:00Z",
            rotation_action="rotate",
            decision_reason="latest_rotate",
        )
        _insert(conn, sleeve_id=slv_id, decision_time="2026-01-01T12:00:00Z", rotation_action="hold")
        row = RotationDecisionRepository(conn).fetch_latest_rotate_action(sleeve_id=slv_id)
        assert row is not None
        assert row["decision_reason"] == "latest_rotate"


def test_fetch_selected_strategy_timeline_orders_incumbent_and_selected(conn) -> None:
    from trading.repositories.book_bridge import default_book_id

    account_id = _account_id(conn, "rot_dec_timeline")
    book_id = default_book_id(conn, account_id)
    repo = RotationDecisionRepository(conn)

    def _book_decision(*, at: str, incumbent: str, selected: str) -> None:
        repo.insert_for_book(
            book_id=book_id,
            decision_time=at,
            incumbent_strategy=incumbent,
            challenger_strategy=selected,
            selected_strategy=selected,
            rotation_action="rotate" if selected != incumbent else "hold",
            cooldown_active=0,
            score_components_json="{}",
            gate_results_json="{}",
            decision_reason="test",
            config_version=None,
            created_at=at,
        )

    _book_decision(at="2026-02-10T00:00:00Z", incumbent="meanrev", selected="trend")
    _book_decision(at="2026-02-01T00:00:00Z", incumbent="trend", selected="meanrev")

    timeline = repo.fetch_selected_strategy_timeline(book_id=book_id)

    assert timeline == [
        ("2026-02-01T00:00:00Z", "trend", "meanrev"),
        ("2026-02-10T00:00:00Z", "meanrev", "trend"),
    ]
    assert repo.fetch_selected_strategy_timeline(book_id=99999) == []
