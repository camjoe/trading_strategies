"""Tests for trading.services.parameters.fetch_parameter_source_view (P7)."""

from __future__ import annotations

import sqlite3

import pytest

from common.time import utc_now_iso
from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.domain.exceptions import NotFoundError
from trading.models.parameters.constants import PARAMETER_SOURCE_DB, PARAMETER_SOURCE_DEFAULT
from trading.repositories.book_bridge import strategy_id_for_label
from trading.services.operational_settings import set_runtime_throttle_settings
from trading.services.parameters import fetch_parameter_source_view


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


class TestBookGroups:
    def test_book_groups_with_missing_settings_rows(self, conn: sqlite3.Connection) -> None:
        account_id = insert_repository_account(conn, name="view_acct")
        insert_test_book(conn, account_id=account_id, name="book_a")

        view = fetch_parameter_source_view(conn, account_name="view_acct")

        mandate = _group(view, "account view_acct / book book_a / mandate")
        assert _entry(mandate, "goal_period").source == PARAMETER_SOURCE_DB
        for concern in ("execution", "options", "rotation"):
            group = _group(view, f"account view_acct / book book_a / {concern}")
            assert group.entries == ()
            assert group.note is not None

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


class TestStrategyGroups:
    def test_strategy_rows_appear(self, conn: sqlite3.Connection) -> None:
        strategy_id_for_label(conn, "trend", now_iso=utc_now_iso())
        conn.commit()

        view = fetch_parameter_source_view(conn)

        strategy = _group(view, "strategy trend")
        assert _entry(strategy, "primitive").value == "trend"
        assert _entry(strategy, "params").value == "{}"
