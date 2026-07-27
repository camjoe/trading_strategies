from __future__ import annotations

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.book_settings import BookRotationSettingsRepository


class TestBookRotationSettingsChangeAudit:
    def test_first_scheduling_write_records_a_change_event_with_null_old_values(self, conn) -> None:
        account_id = insert_repository_account(conn)
        book_id = insert_test_book(conn, account_id=account_id)
        repo = BookRotationSettingsRepository(conn)

        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=1,
            rotation_lookback_days=30,
            rotation_schedule='["trend"]',
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )

        events = repo.fetch_change_events(book_id=book_id)

        assert len(events) == 1
        assert events[0].settings_group == "scheduling"
        assert events[0].book_id == book_id
        assert events[0].changed_fields == {
            "rotation_enabled": {"old": None, "new": 1},
            "rotation_lookback_days": {"old": None, "new": 30},
            "rotation_schedule": {"old": None, "new": '["trend"]'},
        }

    def test_second_write_only_records_changed_fields(self, conn) -> None:
        account_id = insert_repository_account(conn)
        book_id = insert_test_book(conn, account_id=account_id)
        repo = BookRotationSettingsRepository(conn)
        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=1,
            rotation_lookback_days=30,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )

        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=1,
            rotation_lookback_days=45,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T01:00:00Z",
        )

        events = repo.fetch_change_events(book_id=book_id)

        assert len(events) == 2
        assert events[0].changed_fields == {"rotation_lookback_days": {"old": 30, "new": 45}}

    def test_no_op_write_records_no_change_event(self, conn) -> None:
        account_id = insert_repository_account(conn)
        book_id = insert_test_book(conn, account_id=account_id)
        repo = BookRotationSettingsRepository(conn)
        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=0,
            rotation_lookback_days=None,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )

        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=0,
            rotation_lookback_days=None,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T01:00:00Z",
        )

        events = repo.fetch_change_events(book_id=book_id)

        assert len(events) == 1

    def test_policy_change_events_are_scoped_separately_from_scheduling(self, conn) -> None:
        account_id = insert_repository_account(conn)
        book_id = insert_test_book(conn, account_id=account_id)
        repo = BookRotationSettingsRepository(conn)
        repo.upsert_rotation_scheduling(
            book_id=book_id,
            rotation_enabled=1,
            rotation_lookback_days=30,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )
        repo.upsert_rotation_policy(
            book_id=book_id,
            min_trades_in_window=5,
            outperformance_threshold_bps=10.0,
            cooldown_days=3,
            risk_adjusted_return_weight=0.5,
            stability_weight=0.2,
            drawdown_penalty_weight=0.2,
            regime_fit_weight=0.1,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T01:00:00Z",
        )

        events = repo.fetch_change_events(book_id=book_id)

        assert [event.settings_group for event in events] == ["policy", "scheduling"]

    def test_change_events_are_scoped_per_book(self, conn) -> None:
        account_id = insert_repository_account(conn)
        book1_id = insert_test_book(conn, account_id=account_id, name="book1")
        book2_id = insert_test_book(conn, account_id=account_id, name="book2")
        repo = BookRotationSettingsRepository(conn)

        repo.upsert_rotation_scheduling(
            book_id=book1_id,
            rotation_enabled=1,
            rotation_lookback_days=None,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )
        repo.upsert_rotation_scheduling(
            book_id=book2_id,
            rotation_enabled=1,
            rotation_lookback_days=None,
            rotation_schedule=None,
            created_at="2026-07-26T00:00:00Z",
            updated_at="2026-07-26T00:00:00Z",
        )

        assert len(repo.fetch_change_events(book_id=book1_id)) == 1
        assert len(repo.fetch_change_events(book_id=book2_id)) == 1
