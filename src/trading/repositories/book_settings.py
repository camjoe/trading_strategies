from __future__ import annotations

import sqlite3

from trading.models.books.book_execution_settings_record import BookExecutionSettingsRecord
from trading.models.books.book_option_settings_record import BookOptionSettingsRecord
from trading.models.books.book_rotation_settings_record import BookRotationSettingsRecord

# Per-concern typed settings tables, 1:1 with books. A missing row means
# "use code defaults"; a per-row change-audit stays deferred until edit volume
# justifies it.


class BookExecutionSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, book_id: int) -> BookExecutionSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_execution_settings WHERE book_id = ?",
            (int(book_id),),
        ).fetchone()
        return BookExecutionSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert(
        self,
        *,
        book_id: int,
        learning_enabled: int = 0,
        risk_policy: str = "none",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        profit_take_pct: float | None = None,
        max_loss_pct: float | None = None,
        trade_size_pct: float | None = None,
        max_position_pct: float | None = None,
        max_trades_per_run: int | None = None,
        instrument_mode: str = "equity",
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO book_execution_settings (
                book_id, learning_enabled, risk_policy, stop_loss_pct, take_profit_pct,
                profit_take_pct, max_loss_pct, trade_size_pct, max_position_pct,
                max_trades_per_run, instrument_mode, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                learning_enabled = excluded.learning_enabled,
                risk_policy = excluded.risk_policy,
                stop_loss_pct = excluded.stop_loss_pct,
                take_profit_pct = excluded.take_profit_pct,
                profit_take_pct = excluded.profit_take_pct,
                max_loss_pct = excluded.max_loss_pct,
                trade_size_pct = excluded.trade_size_pct,
                max_position_pct = excluded.max_position_pct,
                max_trades_per_run = excluded.max_trades_per_run,
                instrument_mode = excluded.instrument_mode,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                int(learning_enabled),
                risk_policy,
                stop_loss_pct,
                take_profit_pct,
                profit_take_pct,
                max_loss_pct,
                trade_size_pct,
                max_position_pct,
                max_trades_per_run,
                instrument_mode,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()


class BookOptionSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, book_id: int) -> BookOptionSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_option_settings WHERE book_id = ?",
            (int(book_id),),
        ).fetchone()
        return BookOptionSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert(
        self,
        *,
        book_id: int,
        option_strike_offset_pct: float | None = None,
        option_min_dte: int | None = None,
        option_max_dte: int | None = None,
        option_type: str | None = None,
        target_delta_min: float | None = None,
        target_delta_max: float | None = None,
        max_premium_per_trade: float | None = None,
        max_contracts_per_trade: int | None = None,
        iv_rank_min: float | None = None,
        iv_rank_max: float | None = None,
        roll_dte_threshold: int | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO book_option_settings (
                book_id, option_strike_offset_pct, option_min_dte, option_max_dte,
                option_type, target_delta_min, target_delta_max, max_premium_per_trade,
                max_contracts_per_trade, iv_rank_min, iv_rank_max, roll_dte_threshold,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                option_strike_offset_pct = excluded.option_strike_offset_pct,
                option_min_dte = excluded.option_min_dte,
                option_max_dte = excluded.option_max_dte,
                option_type = excluded.option_type,
                target_delta_min = excluded.target_delta_min,
                target_delta_max = excluded.target_delta_max,
                max_premium_per_trade = excluded.max_premium_per_trade,
                max_contracts_per_trade = excluded.max_contracts_per_trade,
                iv_rank_min = excluded.iv_rank_min,
                iv_rank_max = excluded.iv_rank_max,
                roll_dte_threshold = excluded.roll_dte_threshold,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                option_strike_offset_pct,
                option_min_dte,
                option_max_dte,
                option_type,
                target_delta_min,
                target_delta_max,
                max_premium_per_trade,
                max_contracts_per_trade,
                iv_rank_min,
                iv_rank_max,
                roll_dte_threshold,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()


class BookRotationSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch(self, *, book_id: int) -> BookRotationSettingsRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_rotation_settings WHERE book_id = ?",
            (int(book_id),),
        ).fetchone()
        return BookRotationSettingsRecord.from_mapping(dict(row)) if row is not None else None

    def upsert_rotation_scheduling(
        self,
        *,
        book_id: int,
        rotation_enabled: int = 0,
        rotation_lookback_days: int | None = None,
        rotation_schedule: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        # Scheduling-only write: policy columns keep their values when the row
        # already exists; a fresh row gets policy NULLs (code defaults). The
        # mode/optimality/regime/overlay and interval columns are retained on
        # the table (append-only) but are dead config — no longer written.
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings (
                book_id, rotation_enabled, rotation_lookback_days, rotation_schedule,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                rotation_enabled = excluded.rotation_enabled,
                rotation_lookback_days = excluded.rotation_lookback_days,
                rotation_schedule = excluded.rotation_schedule,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                int(rotation_enabled),
                rotation_lookback_days,
                rotation_schedule,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()

    def upsert_rotation_policy(
        self,
        *,
        book_id: int,
        min_trades_in_window: int | None,
        outperformance_threshold_bps: float | None,
        cooldown_days: int | None,
        risk_adjusted_return_weight: float | None,
        stability_weight: float | None,
        drawdown_penalty_weight: float | None,
        cost_penalty_weight: float | None,
        regime_fit_weight: float | None,
        created_at: str,
        updated_at: str,
    ) -> None:
        # Policy-only write: scheduling columns keep their values when the
        # row already exists; a fresh row gets scheduling defaults.
        self._conn.execute(
            """
            INSERT INTO book_rotation_settings (
                book_id, min_trades_in_window, outperformance_threshold_bps,
                cooldown_days, risk_adjusted_return_weight, stability_weight,
                drawdown_penalty_weight, cost_penalty_weight, regime_fit_weight,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                min_trades_in_window = excluded.min_trades_in_window,
                outperformance_threshold_bps = excluded.outperformance_threshold_bps,
                cooldown_days = excluded.cooldown_days,
                risk_adjusted_return_weight = excluded.risk_adjusted_return_weight,
                stability_weight = excluded.stability_weight,
                drawdown_penalty_weight = excluded.drawdown_penalty_weight,
                cost_penalty_weight = excluded.cost_penalty_weight,
                regime_fit_weight = excluded.regime_fit_weight,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                min_trades_in_window,
                outperformance_threshold_bps,
                cooldown_days,
                risk_adjusted_return_weight,
                stability_weight,
                drawdown_penalty_weight,
                cost_penalty_weight,
                regime_fit_weight,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()
