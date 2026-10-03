from __future__ import annotations

import pytest

from tests.support.books import insert_test_book, latest_rotation_decision
from tests.support.repositories import insert_repository_account
from trading.repositories.rotation_decisions import RotationDecisionRepository


def _account_id(conn, name: str = "rot_dec_acct") -> int:
    return insert_repository_account(conn, name=name)


def _book_id(conn, account_id: int) -> int:
    return insert_test_book(conn, account_id=account_id)


def _insert(
    conn,
    *,
    book_id: int,
    decision_time: str,
    rotation_action: str = "hold",
    incumbent_strategy: str = "trend",
    challenger_strategy: str = "meanrev",
    selected_strategy: str = "trend",
    decision_reason: str | None = "threshold_not_met",
) -> int:
    return RotationDecisionRepository(conn).insert_for_book(
        book_id=book_id,
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
        created_at=decision_time,
    )


class TestInsert:
    def test_returns_positive_id(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        row_id = _insert(conn, book_id=bk_id, decision_time="2026-01-01T10:00:00Z")
        assert row_id > 0

    def test_raises_when_lastrowid_missing(self) -> None:
        class _Cursor:
            def __init__(self, *, lastrowid=None) -> None:
                self.lastrowid = lastrowid
                self.rowcount = 1

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        class _Conn:
            def execute(self, *_a, **_kw):
                return _Cursor(lastrowid=None)

            def commit(self):
                pass

        with pytest.raises(ValueError, match="Expected rotation_decisions id after insert"):
            RotationDecisionRepository(_Conn()).insert_for_book(
                book_id=1,
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
                created_at="2026-01-01T00:00:00Z",
            )


class TestFetchLatest:
    def test_returns_none_when_no_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        assert latest_rotation_decision(conn, bk_id) is None

    def test_returns_most_recent_by_decision_time(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T09:00:00Z", decision_reason="first")
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T11:00:00Z", decision_reason="latest")
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T10:00:00Z", decision_reason="middle")
        row = latest_rotation_decision(conn, bk_id)
        assert row is not None
        assert row.decision_reason == "latest"

    def test_isolated_per_book(self, conn) -> None:
        acct_id = _account_id(conn)
        slv_a = _book_id(conn, acct_id)
        bk_b = insert_test_book(conn, account_id=acct_id, name="book_b")
        _insert(conn, book_id=slv_a, decision_time="2026-01-01T10:00:00Z", decision_reason="for_a")
        assert latest_rotation_decision(conn, bk_b) is None


class TestFetchForBook:
    def test_returns_empty_list_when_no_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        assert RotationDecisionRepository(conn).fetch_for_book(book_id=bk_id, limit=10) == []

    def test_limit_is_respected(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        for hour in range(5):
            _insert(conn, book_id=bk_id, decision_time=f"2026-01-01T{hour:02d}:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_book(book_id=bk_id, limit=3)
        assert len(rows) == 3

    def test_ordered_by_decision_time_desc(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T09:00:00Z")
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T11:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_book(book_id=bk_id, limit=10)
        times = [r.decision_time for r in rows]
        assert times == sorted(times, reverse=True)


class TestFetchForBookOnDate:
    def test_returns_only_rows_on_given_date(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T23:59:00Z", decision_reason="before")
        _insert(conn, book_id=bk_id, decision_time="2026-01-02T09:00:00Z", decision_reason="on_date")
        _insert(conn, book_id=bk_id, decision_time="2026-01-03T00:00:00Z", decision_reason="after")
        rows = RotationDecisionRepository(conn).fetch_for_book_on_date(book_id=bk_id, report_date="2026-01-02")
        assert len(rows) == 1
        assert rows[0].decision_reason == "on_date"

    def test_date_boundary_is_exclusive_at_end(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-02T23:59:59Z", decision_reason="last_second")
        _insert(conn, book_id=bk_id, decision_time="2026-01-03T00:00:00Z", decision_reason="next_day")
        rows = RotationDecisionRepository(conn).fetch_for_book_on_date(book_id=bk_id, report_date="2026-01-02")
        assert len(rows) == 1
        assert rows[0].decision_reason == "last_second"

    def test_ordered_by_decision_time_asc(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-02T11:00:00Z")
        _insert(conn, book_id=bk_id, decision_time="2026-01-02T09:00:00Z")
        rows = RotationDecisionRepository(conn).fetch_for_book_on_date(book_id=bk_id, report_date="2026-01-02")
        times = [r.decision_time for r in rows]
        assert times == sorted(times)


class TestFetchLatestRotateAction:
    def test_returns_none_when_no_rotate_decisions(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T10:00:00Z", rotation_action="hold")
        assert RotationDecisionRepository(conn).fetch_latest_rotate_time_for_book(book_id=bk_id) is None

    def test_returns_most_recent_rotate_ignoring_holds(self, conn) -> None:
        acct_id = _account_id(conn)
        bk_id = _book_id(conn, acct_id)
        _insert(
            conn,
            book_id=bk_id,
            decision_time="2026-01-01T09:00:00Z",
            rotation_action="rotate",
            decision_reason="first_rotate",
        )
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T10:00:00Z", rotation_action="hold")
        _insert(
            conn,
            book_id=bk_id,
            decision_time="2026-01-01T11:00:00Z",
            rotation_action="rotate",
            decision_reason="latest_rotate",
        )
        _insert(conn, book_id=bk_id, decision_time="2026-01-01T12:00:00Z", rotation_action="hold")
        # The cooldown source returns the most recent rotate's decision_time, skipping holds.
        latest = RotationDecisionRepository(conn).fetch_latest_rotate_time_for_book(book_id=bk_id)
        assert latest == "2026-01-01T11:00:00Z"


def test_fetch_selected_strategy_timeline_orders_incumbent_and_selected(conn) -> None:
    from tests.support.books import ensure_default_book_id

    account_id = _account_id(conn, "rot_dec_timeline")
    book_id = ensure_default_book_id(conn, account_id)
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
