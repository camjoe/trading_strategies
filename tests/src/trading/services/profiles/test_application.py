import pytest

from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.accounts import get_account
from trading.services.books.book_assignments import get_default_book
from trading.services.profiles import apply_account_profiles


def _rotation_row(conn, account_name: str):
    account = get_account(conn, account_name)
    book_id = default_book_id(conn, int(account["id"]))
    return BookRotationSettingsRepository(conn).fetch(book_id=book_id)


class TestApplyAccountProfiles:
    def test_sets_risk_and_instrument_fields(self, conn) -> None:
        profiles = [
            {
                "name": "prof_a",
                "strategy": "Momentum",
                "initial_cash": 5000,
                "benchmark_ticker": "SPY",
                "descriptive_name": "Profile A",
                "goal_min_return_pct": 2,
                "goal_max_return_pct": 5,
                "goal_period": "monthly",
                "learning_enabled": True,
                "risk_policy": "fixed_stop",
                "stop_loss_pct": 4,
                "instrument_mode": "leaps",
                "option_strike_offset_pct": 5,
                "option_min_dte": 120,
                "option_max_dte": 365,
                "option_type": "call",
                "target_delta_min": 0.25,
                "target_delta_max": 0.55,
                "max_premium_per_trade": 500,
                "max_contracts_per_trade": 2,
                "iv_rank_min": 20,
                "iv_rank_max": 80,
                "roll_dte_threshold": 45,
                "profit_take_pct": 30,
                "max_loss_pct": 20,
            }
        ]

        created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=True)

        assert created == 1
        assert updated == 0
        assert skipped == 0

        account = get_account(conn, "prof_a")
        assert account["descriptive_name"] == "Profile A"
        # Execution settings are book columns (revision 0004).
        book = get_default_book(conn, account_id=account.id)
        assert book is not None
        assert book.risk_policy == "fixed_stop"
        assert book.instrument_mode == "leaps"
        assert book.learning_enabled == 1
        assert account["option_type"] == "call"
        assert float(account["target_delta_min"]) == 0.25
        assert float(account["target_delta_max"]) == 0.55
        assert float(account["iv_rank_min"]) == 20.0
        assert float(account["iv_rank_max"]) == 80.0

    def test_create_missing_false_skips(self, conn):
        profiles = [{"name": "no_create", "initial_cash": 1000}]
        created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=False)
        assert (created, updated, skipped) == (0, 0, 1)

    def test_create_uses_defaults(self, conn):
        profiles = [{"name": "minimal", "initial_cash": 1000, "strategy": "trend"}]
        created, _, _ = apply_account_profiles(conn, profiles, create_missing=True)
        assert created == 1
        account = get_account(conn, "minimal")
        assert account["goal_period"] == "monthly"
        book = get_default_book(conn, account_id=account.id)
        assert book is not None
        assert book.risk_policy == "none"
        assert book.instrument_mode == "equity"
        assert book.learning_enabled == 0

    def test_update_benchmark(self, conn):
        apply_account_profiles(
            conn,
            [{"name": "upd", "initial_cash": 1000, "strategy": "trend"}],
            create_missing=True,
        )
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "upd", "benchmark_ticker": "QQQ"}], create_missing=False
        )
        assert updated == 1
        assert get_account(conn, "upd")["benchmark_ticker"] == "QQQ"

    def test_update_strategy(self, conn):
        apply_account_profiles(
            conn,
            [{"name": "s_acct", "initial_cash": 1000, "strategy": "trend"}],
            create_missing=True,
        )
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "s_acct", "strategy": "breakout"}], create_missing=False
        )
        assert updated == 1
        assert get_account(conn, "s_acct")["strategy"] == "breakout"

    def test_update_configure_fields(self, conn):
        apply_account_profiles(
            conn,
            [{"name": "cfg", "initial_cash": 1000, "strategy": "trend"}],
            create_missing=True,
        )
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "cfg", "risk_policy": "fixed_stop", "stop_loss_pct": 5.0}], create_missing=False
        )
        assert updated == 1
        account = get_account(conn, "cfg")
        book = get_default_book(conn, account_id=account.id)
        assert book is not None
        assert book.risk_policy == "fixed_stop"
        assert book.stop_loss_pct == 5.0

    def test_no_op_skipped(self, conn):
        apply_account_profiles(
            conn,
            [{"name": "noop", "initial_cash": 1000, "strategy": "trend"}],
            create_missing=True,
        )
        _, updated, skipped = apply_account_profiles(
            conn, [{"name": "noop", "initial_cash": 9999}], create_missing=False
        )
        assert updated == 0
        assert skipped == 1

    def test_rejects_null_initial_cash(self, conn):
        with pytest.raises(ValueError, match="initial_cash cannot be null"):
            apply_account_profiles(conn, [{"name": "null_cash", "initial_cash": None}], create_missing=True)


class TestApplyBookRotationSettings:
    def test_created_account_writes_default_book_scheduling(self, conn):
        profiles = [
            {
                "name": "rot_new",
                "strategy": "trend",
                "initial_cash": 2500,
                "rotation": {
                    "enabled": True,
                    "schedule": ["trend", "mean_reversion"],
                    "lookback_days": 45,
                },
            }
        ]

        created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=True)
        assert (created, updated, skipped) == (1, 0, 0)

        row = _rotation_row(conn, "rot_new")
        assert row is not None
        assert row.rotation_enabled == 1
        assert row.rotation_schedule == '["trend","mean_reversion"]'
        assert row.rotation_lookback_days == 45

    def test_existing_account_partial_update_keeps_other_fields(self, conn):
        apply_account_profiles(
            conn,
            [
                {
                    "name": "rot_upd",
                    "initial_cash": 1000,
                    "strategy": "trend",
                    "rotation": {"enabled": True, "schedule": ["trend", "breakout"], "lookback_days": 60},
                }
            ],
            create_missing=True,
        )

        created, updated, skipped = apply_account_profiles(
            conn,
            [{"name": "rot_upd", "rotation": {"schedule": ["trend", "breakout", "mean_reversion"]}}],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        row = _rotation_row(conn, "rot_upd")
        assert row is not None
        assert row.rotation_enabled == 1
        assert row.rotation_schedule == '["trend","breakout","mean_reversion"]'
        assert row.rotation_lookback_days == 60

    def test_rejects_zero_lookback_days(self, conn):
        with pytest.raises(ValueError, match="rotation.lookback_days"):
            apply_account_profiles(
                conn,
                [
                    {
                        "name": "bad_rot_lookback",
                        "initial_cash": 1000,
                        "strategy": "trend",
                        "rotation": {"lookback_days": 0},
                    }
                ],
                create_missing=True,
            )

    def test_rejects_unknown_schedule_strategy(self, conn):
        apply_account_profiles(
            conn,
            [{"name": "bad_rot2", "initial_cash": 1000, "strategy": "trend"}],
            create_missing=True,
        )
        with pytest.raises(ValueError, match="rotation.schedule"):
            apply_account_profiles(
                conn,
                [{"name": "bad_rot2", "rotation": {"schedule": ["trend", "mystery_strategy"]}}],
                create_missing=False,
            )

    def test_account_columns_stay_untouched(self, conn):
        # Rotation is book-owned (ADR 014): applying rotation config writes
        # book settings only. The account rotation columns were removed
        # outright in revision 0003, so writing them is structurally impossible.
        apply_account_profiles(
            conn,
            [
                {
                    "name": "rot_cols",
                    "initial_cash": 1000,
                    "strategy": "trend",
                    "rotation": {"enabled": True, "schedule": ["trend", "breakout"]},
                }
            ],
            create_missing=True,
        )

        account_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(accounts)")}
        assert not {name for name in account_columns if name.startswith("rotation_")}

    def test_trade_universes_stored_on_create(self, conn) -> None:
        import json

        apply_account_profiles(
            conn,
            [
                {
                    "name": "acct_with_universe",
                    "strategy": "Momentum",
                    "initial_cash": 5000,
                    "benchmark_ticker": "SPY",
                    "trade_universes": ["large_cap", "growth"],
                }
            ],
            create_missing=True,
        )

        account = get_account(conn, "acct_with_universe")
        raw = account["trade_universes"]
        assert raw is not None
        assert json.loads(raw) == ["large_cap", "growth"]

    def test_trade_universes_updated_on_update(self, conn) -> None:
        import json

        apply_account_profiles(
            conn,
            [{"name": "upd_universe", "strategy": "trend", "initial_cash": 5000}],
            create_missing=True,
        )

        apply_account_profiles(
            conn,
            [{"name": "upd_universe", "trade_universes": ["dividend"]}],
            create_missing=False,
        )

        account = get_account(conn, "upd_universe")
        raw = account["trade_universes"]
        assert raw is not None
        assert json.loads(raw) == ["dividend"]
