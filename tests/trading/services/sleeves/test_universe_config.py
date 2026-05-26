"""Tests for trading.services.sleeves.universe_config."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve
from trading.services.sleeves.universe_config import configure_sleeve_trade_universes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sleeve(conn: sqlite3.Connection) -> int:
    account_id = insert_repository_account(conn, name="uni_acct")
    return insert_test_sleeve(conn, account_id=account_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConfigureSleeveTradeUniverses:
    def test_none_names_clears_override(self, conn: sqlite3.Connection) -> None:
        sleeve_id = _make_sleeve(conn)
        with patch("trading.services.sleeves.universe_config.list_available_universes", return_value=["large_cap"]):
            configure_sleeve_trade_universes(conn, sleeve_id=sleeve_id, names=None)
        row = conn.execute("SELECT trade_universes FROM strategy_sleeves WHERE id = ?", (sleeve_id,)).fetchone()
        assert row["trade_universes"] is None

    def test_empty_names_clears_override(self, conn: sqlite3.Connection) -> None:
        sleeve_id = _make_sleeve(conn)
        with patch("trading.services.sleeves.universe_config.list_available_universes", return_value=["large_cap"]):
            configure_sleeve_trade_universes(conn, sleeve_id=sleeve_id, names=[])
        row = conn.execute("SELECT trade_universes FROM strategy_sleeves WHERE id = ?", (sleeve_id,)).fetchone()
        assert row["trade_universes"] is None

    def test_valid_names_serialised_as_json(self, conn: sqlite3.Connection) -> None:
        sleeve_id = _make_sleeve(conn)
        with patch(
            "trading.services.sleeves.universe_config.list_available_universes",
            return_value=["large_cap", "growth"],
        ):
            configure_sleeve_trade_universes(conn, sleeve_id=sleeve_id, names=["large_cap", "growth"])
        row = conn.execute("SELECT trade_universes FROM strategy_sleeves WHERE id = ?", (sleeve_id,)).fetchone()
        assert row["trade_universes"] == '["large_cap","growth"]'

    def test_unknown_name_raises_value_error(self, conn: sqlite3.Connection) -> None:
        sleeve_id = _make_sleeve(conn)
        with patch(
            "trading.services.sleeves.universe_config.list_available_universes",
            return_value=["large_cap"],
        ):
            with pytest.raises(ValueError, match="Unknown universe name"):
                configure_sleeve_trade_universes(conn, sleeve_id=sleeve_id, names=["nonexistent"])

    def test_partial_unknown_names_raises_with_unknown_in_message(self, conn: sqlite3.Connection) -> None:
        sleeve_id = _make_sleeve(conn)
        with patch(
            "trading.services.sleeves.universe_config.list_available_universes",
            return_value=["large_cap"],
        ):
            with pytest.raises(ValueError, match="bad_universe"):
                configure_sleeve_trade_universes(conn, sleeve_id=sleeve_id, names=["large_cap", "bad_universe"])
