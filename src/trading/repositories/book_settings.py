from __future__ import annotations

import sqlite3

from trading.models.books.book_rotation_settings_record import BookRotationSettingsRecord

# Rotation is the one remaining 1:1 settings table (large, coherent, sparse).
# A missing row means "use code defaults"; a per-row change-audit stays
# deferred until edit volume justifies it. Execution and option settings are
# columns on books since revisions 0004/0005.


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
