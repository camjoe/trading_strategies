"""Seed the clean-schema catalog tables from code and legacy account config.

Two idempotent bootstrap passes (P3 Phase D):

- `seed_strategy_catalog` re-creates the code registry's strategies as
  `strategies` rows (primitive + default knobs, D5) so nothing is lost when
  strategies go data.
- `ensure_default_books` gives every account its real default book
  (D7) and copies the account's legacy settings columns into the per-concern
  book settings tables (D4) so book-keyed reads have data to stand on.
"""

from __future__ import annotations

import json
import sqlite3

from common.coercion import row_expect_float, row_expect_int, row_expect_str, row_float, row_int, row_str
from common.time import utc_now_iso
from trading.domain.strategy_signals import PRIMITIVE_CATALOG
from trading.repositories.strategies import StrategyRepository
from trading.repositories.books import BookRepository
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_settings import (
    BookExecutionSettingsRepository,
    BookOptionSettingsRepository,
    BookRotationSettingsRepository,
)


def seed_strategy_catalog(conn: sqlite3.Connection, *, now_iso: str | None = None) -> int:
    """Insert a strategies row per code primitive that has no row yet; returns rows added."""
    now = now_iso or utc_now_iso()
    repo = StrategyRepository(conn)
    inserted = 0
    for primitive in sorted(PRIMITIVE_CATALOG):
        spec = PRIMITIVE_CATALOG[primitive]
        if repo.fetch_by_key(strategy_key=primitive) is not None:
            continue
        repo.insert(
            strategy_key=primitive,
            primitive=primitive,
            params_json=json.dumps(dict(spec.knob_schema), sort_keys=True),
            style=spec.style,
            required_features=json.dumps(list(spec.required_features)) if spec.required_features else None,
            description=spec.description or None,
            status="draft",
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        inserted += 1
    return inserted


def _copy_book_settings_from_account(
    conn: sqlite3.Connection,
    *,
    account: sqlite3.Row,
    book_id: int,
    now: str,
) -> None:
    row = dict(account)
    BookExecutionSettingsRepository(conn).upsert(
        book_id=book_id,
        learning_enabled=row_expect_int(row, "learning_enabled"),
        risk_policy=row_expect_str(row, "risk_policy"),
        stop_loss_pct=row_float(row, "stop_loss_pct"),
        take_profit_pct=row_float(row, "take_profit_pct"),
        profit_take_pct=row_float(row, "profit_take_pct"),
        max_loss_pct=row_float(row, "max_loss_pct"),
        trade_size_pct=row_float(row, "trade_size_pct"),
        max_position_pct=row_float(row, "max_position_pct"),
        max_trades_per_run=None,
        instrument_mode=row_expect_str(row, "instrument_mode"),
        created_at=now,
        updated_at=now,
    )
    if row_expect_str(row, "instrument_mode") == "leaps":
        BookOptionSettingsRepository(conn).upsert(
            book_id=book_id,
            option_strike_offset_pct=row_float(row, "option_strike_offset_pct"),
            option_min_dte=row_int(row, "option_min_dte"),
            option_max_dte=row_int(row, "option_max_dte"),
            option_type=row_str(row, "option_type"),
            target_delta_min=row_float(row, "target_delta_min"),
            target_delta_max=row_float(row, "target_delta_max"),
            max_premium_per_trade=row_float(row, "max_premium_per_trade"),
            max_contracts_per_trade=row_int(row, "max_contracts_per_trade"),
            iv_rank_min=row_float(row, "iv_rank_min"),
            iv_rank_max=row_float(row, "iv_rank_max"),
            roll_dte_threshold=row_int(row, "roll_dte_threshold"),
            created_at=now,
            updated_at=now,
        )

    strategy_repo = StrategyRepository(conn)

    def _strategy_id_for(name_key: str) -> int | None:
        name = row_str(row, name_key)
        if not name:
            return None
        record = strategy_repo.fetch_by_key(strategy_key=name.strip().lower())
        return record.id if record is not None else None

    BookRotationSettingsRepository(conn).upsert(
        book_id=book_id,
        rotation_enabled=row_expect_int(row, "rotation_enabled"),
        rotation_mode=row_str(row, "rotation_mode"),
        rotation_optimality_mode=row_str(row, "rotation_optimality_mode"),
        rotation_interval_days=row_int(row, "rotation_interval_days"),
        rotation_interval_minutes=row_int(row, "rotation_interval_minutes"),
        rotation_lookback_days=row_int(row, "rotation_lookback_days"),
        rotation_schedule=row_str(row, "rotation_schedule"),
        regime_strategy_risk_on_id=_strategy_id_for("rotation_regime_strategy_risk_on"),
        regime_strategy_neutral_id=_strategy_id_for("rotation_regime_strategy_neutral"),
        regime_strategy_risk_off_id=_strategy_id_for("rotation_regime_strategy_risk_off"),
        overlay_mode=row_str(row, "rotation_overlay_mode"),
        overlay_min_tickers=row_int(row, "rotation_overlay_min_tickers"),
        overlay_confidence_threshold=row_float(row, "rotation_overlay_confidence_threshold"),
        overlay_watchlist=row_str(row, "rotation_overlay_watchlist"),
        created_at=now,
        updated_at=now,
    )


def ensure_default_books(conn: sqlite3.Connection, *, now_iso: str | None = None) -> int:
    """Create the real default book (D7) + settings rows for accounts missing one.

    Also opens the book's strategy assignment from the account's legacy strategy
    label when the seeded catalog knows it. Returns books created.
    """
    now = now_iso or utc_now_iso()
    book_repo = BookRepository(conn)
    assignment_repo = BookAssignmentRepository(conn)
    strategy_repo = StrategyRepository(conn)

    accounts = conn.execute("SELECT * FROM accounts ORDER BY id ASC").fetchall()
    created = 0
    for account in accounts:
        account_id = row_expect_int(dict(account), "id")
        if book_repo.fetch_default_for_account(account_id=account_id) is not None:
            continue
        initial_cash = row_expect_float(dict(account), "initial_cash")
        book_id = book_repo.insert(
            account_id=account_id,
            name="default",
            is_default=1,
            start_equity=initial_cash,
            current_cash=initial_cash,
            current_equity=initial_cash,
            trade_universes=row_str(dict(account), "trade_universes"),
            goal_min_return_pct=row_float(dict(account), "goal_min_return_pct"),
            goal_max_return_pct=row_float(dict(account), "goal_max_return_pct"),
            goal_period=row_str(dict(account), "goal_period"),
            created_at=now,
            updated_at=now,
        )
        _copy_book_settings_from_account(conn, account=account, book_id=book_id, now=now)

        legacy_strategy = row_str(dict(account), "strategy")
        if legacy_strategy:
            record = strategy_repo.fetch_by_key(strategy_key=legacy_strategy.strip().lower())
            if record is not None:
                assignment_repo.assign_strategy(
                    book_id=book_id,
                    strategy_id=record.id,
                    effective_from=now,
                    created_at=now,
                    updated_at=now,
                )
        created += 1
    return created
