"""Tests for trading.services.books.rotation.engine.resolve_rotation_policy_config."""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.books import insert_test_book
from tests.support.repositories import insert_repository_account
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.books.rotation.engine import (
    DEFAULT_MIN_TRADES_IN_WINDOW,
    DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS,
    DEFAULT_ROTATION_COOLDOWN_DAYS,
    RotationPolicyConfig,
    resolve_rotation_policy_config,
)


@pytest.fixture
def book_id(conn: sqlite3.Connection) -> int:
    account_id = insert_repository_account(conn, name="policy_acct")
    return insert_test_book(
        conn,
        account_id=account_id,
        name="book_a",
        start_equity=10_000.0,
        current_cash=10_000.0,
        current_equity=10_000.0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_missing_row_falls_back_to_code_defaults(conn: sqlite3.Connection, book_id: int) -> None:
    config = resolve_rotation_policy_config(conn, book_id=book_id, rolling_window_days=45, config_version="v1")

    assert config.rolling_window_days == 45
    assert config.config_version == "v1"
    assert config.min_trades_in_window == DEFAULT_MIN_TRADES_IN_WINDOW
    assert config.outperformance_threshold_bps == DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS
    assert config.cooldown_days == DEFAULT_ROTATION_COOLDOWN_DAYS
    assert config.stability_weight == RotationPolicyConfig().stability_weight


def test_null_policy_fields_fall_back_per_field(conn: sqlite3.Connection, book_id: int) -> None:
    BookRotationSettingsRepository(conn).upsert_rotation_policy(
        book_id=book_id,
        min_trades_in_window=None,
        outperformance_threshold_bps=None,
        cooldown_days=3,
        risk_adjusted_return_weight=None,
        stability_weight=0.5,
        drawdown_penalty_weight=None,
        regime_fit_weight=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    config = resolve_rotation_policy_config(conn, book_id=book_id, rolling_window_days=30)

    assert config.cooldown_days == 3
    assert config.stability_weight == 0.5
    assert config.min_trades_in_window == DEFAULT_MIN_TRADES_IN_WINDOW
    assert config.outperformance_threshold_bps == DEFAULT_OUTPERFORMANCE_THRESHOLD_BPS
    assert config.risk_adjusted_return_weight == RotationPolicyConfig().risk_adjusted_return_weight


def test_full_row_overrides_every_policy_field(conn: sqlite3.Connection, book_id: int) -> None:
    BookRotationSettingsRepository(conn).upsert_rotation_policy(
        book_id=book_id,
        min_trades_in_window=5,
        outperformance_threshold_bps=50.0,
        cooldown_days=14,
        risk_adjusted_return_weight=0.9,
        stability_weight=0.4,
        drawdown_penalty_weight=0.3,
        regime_fit_weight=0.15,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    config = resolve_rotation_policy_config(conn, book_id=book_id, rolling_window_days=30)

    assert config.min_trades_in_window == 5
    assert config.outperformance_threshold_bps == 50.0
    assert config.cooldown_days == 14
    assert config.risk_adjusted_return_weight == 0.9
    assert config.stability_weight == 0.4
    assert config.drawdown_penalty_weight == 0.3
    assert config.regime_fit_weight == 0.15
