"""Tests for trading.services.parameters.fetch_parameter_source_view."""

from __future__ import annotations

import sqlite3

import pytest

from common.time import utc_now_iso
from tests.support.books import insert_test_book, set_test_book_rotation_scheduling
from tests.support.repositories import insert_repository_account
from trading.domain.exceptions import NotFoundError
from trading.models.parameters import PARAMETER_SOURCE_DB, PARAMETER_SOURCE_DEFAULT
from trading.repositories.strategies import StrategyRepository
from trading.services.books.rotation.engine import BookRotationScheduleConfig, RotationPolicyConfig
from trading.services.operational_settings.mutations import set_runtime_throttle_settings
from trading.services.parameters.mutations import update_book_rotation_policy
from trading.services.parameters.view import fetch_parameter_source_view


def _group(view, scope: str):
    match = [group for group in view.groups if group.scope == scope]
    assert match, f"missing group: {scope} (have {[g.scope for g in view.groups]})"
    return match[0]


def _entry(group, name: str):
    match = [entry for entry in group.entries if entry.name == name]
    assert match, f"missing entry {name} in {group.scope}"
    return match[0]


class TestGlobalGroups:
    def test_defaults_without_settings_row(self, conn: sqlite3.Connection) -> None:
        view = fetch_parameter_source_view(conn)

        throttle = _group(view, "global / trade throttle")
        assert throttle.note is not None
        assert _entry(throttle, "max_trades_per_day").value == "none"
        assert _entry(throttle, "max_trades_per_day").source == PARAMETER_SOURCE_DEFAULT
        evaluation = _group(view, "global / evaluation confidence")
        assert _entry(evaluation, "backtest_evidence_weight").value == "0.6"

    def test_db_source_after_settings_write(self, conn: sqlite3.Connection) -> None:
        set_runtime_throttle_settings(
            conn,
            runtime_max_trades_per_day=15,
            runtime_max_trades_per_minute=None,
            updated_at=utc_now_iso(),
        )

        view = fetch_parameter_source_view(conn)

        throttle = _group(view, "global / trade throttle")
        assert throttle.note is None
        entry = _entry(throttle, "max_trades_per_day")
        assert entry.value == "15"
        assert entry.source == PARAMETER_SOURCE_DB

        unlimited = _entry(throttle, "max_trades_per_minute")
        assert unlimited.value == "none"
        assert unlimited.source == PARAMETER_SOURCE_DEFAULT

        evaluation = _group(view, "global / evaluation confidence")
        evidence_weight = _entry(evaluation, "backtest_evidence_weight")
        assert evidence_weight.value == "0.6"
        assert evidence_weight.source == PARAMETER_SOURCE_DEFAULT

        promotion = _group(view, "global / promotion policy")
        confidence = _entry(promotion, "min_live_overall_confidence")
        assert confidence.value == "0.6"
        assert confidence.source == PARAMETER_SOURCE_DEFAULT


class TestBookGroups:
    def test_book_groups_with_missing_settings_rows(self, conn: sqlite3.Connection) -> None:
        account_id = insert_repository_account(conn, name="view_acct")
        insert_test_book(conn, account_id=account_id, name="book_a")

        view = fetch_parameter_source_view(conn, account_name="view_acct")

        mandate = _group(view, "account view_acct / book book_a / mandate")
        assert _entry(mandate, "goal_period").source == PARAMETER_SOURCE_DB
        # Execution and option settings are book columns (revisions
        # 0004/0005): a book row always exists, so both groups are always
        # populated and db-sourced.
        execution = _group(view, "account view_acct / book book_a / execution")
        assert execution.note is None
        assert _entry(execution, "risk_policy").value == "none"
        assert _entry(execution, "risk_policy").source == PARAMETER_SOURCE_DB
        options = _group(view, "account view_acct / book book_a / options")
        assert options.note is None
        assert _entry(options, "option_type").value == "none"
        assert _entry(options, "option_type").source == PARAMETER_SOURCE_DB
        # The rotation group always shows the effective policy: a missing row
        # means every policy field is the code default.
        rotation = _group(view, "account view_acct / book book_a / rotation")
        assert rotation.note is not None
        assert rotation.entries != ()
        assert all(entry.source == PARAMETER_SOURCE_DEFAULT for entry in rotation.entries)
        min_trades = _entry(rotation, "min_trades_in_window")
        assert min_trades.value == str(RotationPolicyConfig().min_trades_in_window)

    def test_rotation_policy_partial_row_resolves_per_field(self, conn: sqlite3.Connection) -> None:
        account_id = insert_repository_account(conn, name="view_acct")
        insert_test_book(conn, account_id=account_id, name="book_a")
        update_book_rotation_policy(conn, account_name="view_acct", book_name="book_a", updates={"cooldown_days": 10})

        view = fetch_parameter_source_view(conn, account_name="view_acct")

        rotation = _group(view, "account view_acct / book book_a / rotation")
        assert rotation.note is None
        cooldown = _entry(rotation, "cooldown_days")
        assert cooldown.value == "10"
        assert cooldown.source == PARAMETER_SOURCE_DB
        min_trades = _entry(rotation, "min_trades_in_window")
        assert min_trades.value == str(RotationPolicyConfig().min_trades_in_window)
        assert min_trades.source == PARAMETER_SOURCE_DEFAULT

    def test_account_filter_unknown_name_raises(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(NotFoundError):
            fetch_parameter_source_view(conn, account_name="missing")

    def test_account_filter_limits_books(self, conn: sqlite3.Connection) -> None:
        first = insert_repository_account(conn, name="first_acct")
        second = insert_repository_account(conn, name="second_acct")
        insert_test_book(conn, account_id=first, name="book_a")
        insert_test_book(conn, account_id=second, name="book_b")

        view = fetch_parameter_source_view(conn, account_name="first_acct")

        scopes = [group.scope for group in view.groups]
        assert any("first_acct" in scope for scope in scopes)
        assert not any("second_acct" in scope for scope in scopes)


class TestBookRotationSchedulingDisplay:
    def test_scheduling_defaults_when_no_row(self, conn: sqlite3.Connection) -> None:
        account_id = insert_repository_account(conn, name="acct_rotation")
        insert_test_book(conn, account_id=account_id, name="book_a")

        view = fetch_parameter_source_view(conn, account_name="acct_rotation")

        rotation = _group(view, "account acct_rotation / book book_a / rotation")
        enabled = _entry(rotation, "rotation_enabled")
        assert enabled.value == "False"
        assert enabled.source == PARAMETER_SOURCE_DEFAULT
        lookback = _entry(rotation, "rotation_lookback_days")
        assert lookback.value == str(BookRotationScheduleConfig().lookback_days)
        assert lookback.source == PARAMETER_SOURCE_DEFAULT
        assert _entry(rotation, "rotation_schedule").value == "none"

    def test_scheduling_db_source_when_set(self, conn: sqlite3.Connection) -> None:
        account_id = insert_repository_account(conn, name="acct_rotation")
        book_id = insert_test_book(conn, account_id=account_id, name="book_a")
        set_test_book_rotation_scheduling(
            conn, book_id=book_id, enabled=1, schedule=["trend", "meanrev"], lookback_days=45
        )

        view = fetch_parameter_source_view(conn, account_name="acct_rotation")

        rotation = _group(view, "account acct_rotation / book book_a / rotation")
        enabled = _entry(rotation, "rotation_enabled")
        assert enabled.value == "True"
        assert enabled.source == PARAMETER_SOURCE_DB
        lookback = _entry(rotation, "rotation_lookback_days")
        assert lookback.value == "45"
        assert lookback.source == PARAMETER_SOURCE_DB
        schedule = _entry(rotation, "rotation_schedule")
        assert schedule.value == '["trend","meanrev"]'
        assert schedule.source == PARAMETER_SOURCE_DB


class TestStrategyGroups:
    def test_strategy_rows_appear(self, conn: sqlite3.Connection) -> None:
        StrategyRepository(conn).ensure_id_for_label(label="trend", now_iso=utc_now_iso())
        conn.commit()

        view = fetch_parameter_source_view(conn)

        strategy = _group(view, "strategy trend")
        assert _entry(strategy, "primitive").value == "trend"
        assert _entry(strategy, "params").value == "{}"
